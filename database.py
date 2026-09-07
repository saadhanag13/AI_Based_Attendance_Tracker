"""SQLite persistence layer for the attendance system.

Uses Python's standard library ``sqlite3`` so no extra dependency is required.
The schema tracks students, per-model face encodings, classes, sessions
(one per class per day) and attendance records.

Call :func:`init_db` once at startup to create tables if they do not exist.
Use :func:`connect` to obtain a connection that automatically enables foreign
keys and row access by column name.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).parent / "attendance.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS students (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    photo           TEXT,
    gender          TEXT,
    -- JSON: {"filename": "aditya.jpg", "image_base64": "<data>"}
    image_metadata  TEXT,
    active          INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Face embeddings are stored per (student, model) so the active recognition
-- model can be swapped later without invalidating encodings.
CREATE TABLE IF NOT EXISTS student_encodings (
    student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    model_name  TEXT    NOT NULL,
    embedding   BLOB    NOT NULL,
    dim         INTEGER NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (student_id, model_name)
);

CREATE TABLE IF NOT EXISTS classes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL UNIQUE,
    subject         TEXT,
    student_count   INTEGER,
    batch_year      TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Ground-truth roster: which students are enrolled in a class. Attendance
-- tracking for a class is validated against this enrollment.
CREATE TABLE IF NOT EXISTS class_enrollment (
    class_id    INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (class_id, student_id)
);

-- A "session" is an attendance roster for one class on one date. A class may
-- have several sessions on the same date (e.g. morning/afternoon periods), so
-- uniqueness is NOT enforced on (class_id, date); ``label`` disambiguates them.
-- ``photo`` stores the uploaded group image ({filename, image_base64}) that
-- produced the session's attendance, for audit/reporting purposes.
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id    INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    date        TEXT    NOT NULL,
    label       TEXT,
    photo       TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS attendance (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    status      TEXT    NOT NULL DEFAULT 'present',
    distance    REAL,
    confidence  REAL,
    source      TEXT,
    marked_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (session_id, student_id)
);

CREATE INDEX IF NOT EXISTS idx_student_encodings_model ON student_encodings(model_name);
CREATE INDEX IF NOT EXISTS idx_sessions_class_date ON sessions(class_id, date);
CREATE INDEX IF NOT EXISTS idx_attendance_session ON attendance(session_id);
"""


@contextmanager
def connect(db_path: Path | str = DEFAULT_DB_PATH) -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection with foreign keys and row access enabled.

    Commits on success and rolls back on any exception.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path | str = DEFAULT_DB_PATH) -> None:
    """Create all tables if they do not already exist.

    Foreign keys are disabled here because schema migrations may need to rebuild
    a parent table (e.g. ``sessions``) that other tables reference. All normal
    read/write operations go through :func:`connect`, which re-enables them.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.executescript(SCHEMA_SQL)
        _migrate(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Idempotently add columns/tables introduced after the initial schema."""
    student_cols = {r[1] for r in conn.execute("PRAGMA table_info(students)")}
    if "image_metadata" not in student_cols:
        conn.execute("ALTER TABLE students ADD COLUMN image_metadata TEXT")
    if "gender" not in student_cols:
        conn.execute("ALTER TABLE students ADD COLUMN gender TEXT")

    class_cols = {r[1] for r in conn.execute("PRAGMA table_info(classes)")}
    # New fields for the class record (subject / declared student count / batch year).
    for column, ddl in {
        "subject": "TEXT",
        "student_count": "INTEGER",
        "batch_year": "TEXT",
    }.items():
        if column not in class_cols:
            conn.execute(f"ALTER TABLE classes ADD COLUMN {column} {ddl}")

    # Legacy columns (kept for backward compatibility with existing DBs).
    for column, ddl in {
        "description": "TEXT",
        "academic_year": "TEXT",
        "semester": "TEXT",
        "schedule": "TEXT",
    }.items():
        if column not in class_cols:
            conn.execute(f"ALTER TABLE classes ADD COLUMN {column} {ddl}")

    _migrate_sessions(conn)

    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    if "class_enrollment" not in tables:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS class_enrollment (
                class_id    INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
                student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (class_id, student_id)
            )
            """
        )


def _migrate_sessions(conn: sqlite3.Connection) -> None:
    """Recreate the sessions table to allow multiple sessions per class+date.

    The original schema enforced ``UNIQUE (class_id, date)`` which forbids two
    sessions on the same day. This rebuilds the table (dropping the unique
    constraint) and adds a ``label`` column to disambiguate sessions, preserving
    existing rows.
    """
    cols = {r[1] for r in conn.execute("PRAGMA table_info(sessions)")}
    has_label = "label" in cols
    has_unique = any(
        r["origin"] == "u"
        for r in conn.execute("PRAGMA index_list('sessions')")
    )
    if has_label and not has_unique:
        return

    label_expr = "label" if has_label else "NULL AS label"
    photo_expr = "photo" if "photo" in cols else "NULL AS photo"
    conn.execute("DROP TABLE IF EXISTS sessions_new")
    conn.execute(
        """
        CREATE TABLE sessions_new (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id    INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
            date        TEXT    NOT NULL,
            label       TEXT,
            photo       TEXT,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "INSERT INTO sessions_new (id, class_id, date, label, photo, created_at) "
        "SELECT id, class_id, date, " + label_expr + ", " + photo_expr +
        ", created_at FROM sessions"
    )
    conn.execute("DROP TABLE sessions")
    conn.execute("ALTER TABLE sessions_new RENAME TO sessions")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_class_date ON sessions(class_id, date)"
    )
