"""Data-access layer over the SQLite database.

All SQL lives here; higher layers work with plain dicts / ``sqlite3.Row``
objects keyed by the schema columns. Use :mod:`database.connect` to get a
connection and pass it to these functions.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import sqlite3

# --------------------------------------------------------------------------- #
# Students & encodings
# --------------------------------------------------------------------------- #


def upsert_student(
    conn: sqlite3.Connection,
    name: str,
    photo: str | None = None,
    gender: str | None = None,
) -> int:
    """Insert a student, or return the existing id when the name is already present."""
    row = conn.execute(
        "SELECT id FROM students WHERE name = ?", (name,)
    ).fetchone()
    if row is not None:
        if photo is not None:
            conn.execute(
                "UPDATE students SET photo = ? WHERE id = ?", (photo, row["id"])
            )
        if gender is not None:
            conn.execute(
                "UPDATE students SET gender = ? WHERE id = ?", (gender, row["id"])
            )
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO students (name, photo, gender) VALUES (?, ?, ?)",
        (name, photo, gender),
    )
    return int(cur.lastrowid)


def set_student_image(
    conn: sqlite3.Connection,
    student_id: int,
    filename: str,
    image_base64: str,
) -> None:
    """Store a student's image metadata (filename + base64 payload)."""
    import json

    metadata = json.dumps({"filename": filename, "image_base64": image_base64})
    conn.execute(
        "UPDATE students SET image_metadata = ? WHERE id = ?", (metadata, student_id)
    )


def get_student_image(
    conn: sqlite3.Connection, student_id: int
) -> dict[str, str] | None:
    """Return the stored {filename, image_base64} metadata for a student."""
    import json

    row = conn.execute(
        "SELECT image_metadata FROM students WHERE id = ?", (student_id,)
    ).fetchone()
    if row is None or not row["image_metadata"]:
        return None
    return json.loads(row["image_metadata"])


def list_students(conn: sqlite3.Connection, active_only: bool = True) -> list[sqlite3.Row]:
    query = "SELECT * FROM students"
    if active_only:
        query += " WHERE active = 1"
    query += " ORDER BY name"
    return list(conn.execute(query))


def save_encoding(
    conn: sqlite3.Connection,
    student_id: int,
    model_name: str,
    embedding: np.ndarray,
) -> None:
    """Store (or replace) a face embedding for a student under a model name."""
    embedding = np.asarray(embedding, dtype=np.float32)
    conn.execute(
        """
        INSERT INTO student_encodings (student_id, model_name, embedding, dim)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(student_id, model_name)
        DO UPDATE SET embedding = excluded.embedding, dim = excluded.dim,
                      created_at = datetime('now')
        """,
        (student_id, model_name, embedding.tobytes(), int(embedding.size)),
    )


def get_encodings(
    conn: sqlite3.Connection, model_name: str
) -> list[dict[str, Any]]:
    """Return active students with their embeddings for a given model."""
    rows = conn.execute(
        """
        SELECT s.id AS student_id, s.name, se.embedding, se.dim
        FROM students s
        JOIN student_encodings se ON se.student_id = s.id
        WHERE s.active = 1 AND se.model_name = ?
        ORDER BY s.name
        """,
        (model_name,),
    )
    result = []
    for row in rows:
        embedding = np.frombuffer(row["embedding"], dtype=np.float32).reshape(row["dim"])
        result.append(
            {"student_id": row["student_id"], "name": row["name"], "embedding": embedding}
        )
    return result


def count_students(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM students WHERE active = 1").fetchone()
    return int(row["n"])


def get_enrolled_encodings(
    conn: sqlite3.Connection, class_id: int, model_name: str
) -> list[dict[str, Any]]:
    """Return embeddings for the students enrolled in a class (ground truth)."""
    rows = conn.execute(
        """
        SELECT s.id AS student_id, s.name, se.embedding, se.dim
        FROM students s
        JOIN class_enrollment ce ON ce.student_id = s.id
        JOIN student_encodings se ON se.student_id = s.id
        WHERE ce.class_id = ? AND s.active = 1 AND se.model_name = ?
        ORDER BY s.name
        """,
        (class_id, model_name),
    )
    result = []
    for row in rows:
        embedding = np.frombuffer(row["embedding"], dtype=np.float32).reshape(row["dim"])
        result.append(
            {"student_id": row["student_id"], "name": row["name"], "embedding": embedding}
        )
    return result


# --------------------------------------------------------------------------- #
# Classes & sessions
# --------------------------------------------------------------------------- #


def create_class(
    conn: sqlite3.Connection,
    name: str,
    subject: str = "",
    student_count: int | None = None,
    batch_year: str = "",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO classes (name, subject, student_count, batch_year)
        VALUES (?, ?, ?, ?)
        """,
        (name, subject, student_count, batch_year),
    )
    return int(cur.lastrowid)


def update_class(
    conn: sqlite3.Connection,
    class_id: int,
    subject: str | None = None,
    student_count: int | None = None,
    batch_year: str | None = None,
) -> None:
    if subject is not None:
        conn.execute(
            "UPDATE classes SET subject = ? WHERE id = ?", (subject, class_id)
        )
    if student_count is not None:
        conn.execute(
            "UPDATE classes SET student_count = ? WHERE id = ?",
            (student_count, class_id),
        )
    if batch_year is not None:
        conn.execute(
            "UPDATE classes SET batch_year = ? WHERE id = ?", (batch_year, class_id)
        )


def list_classes(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(conn.execute("SELECT * FROM classes ORDER BY name"))


def get_class(conn: sqlite3.Connection, class_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()


# -- enrollment (ground truth) ------------------------------------------------


def set_enrollment(conn: sqlite3.Connection, class_id: int, student_ids: list[int]) -> None:
    """Replace the class roster (ground truth) with the given student ids."""
    conn.execute("DELETE FROM class_enrollment WHERE class_id = ?", (class_id,))
    conn.executemany(
        "INSERT OR IGNORE INTO class_enrollment (class_id, student_id) VALUES (?, ?)",
        [(class_id, sid) for sid in student_ids],
    )


def enrolled_student_ids(conn: sqlite3.Connection, class_id: int) -> set[int]:
    return {
        int(r["student_id"])
        for r in conn.execute(
            "SELECT student_id FROM class_enrollment WHERE class_id = ?", (class_id,)
        )
    }


def enrolled_students(conn: sqlite3.Connection, class_id: int) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT s.* FROM students s
            JOIN class_enrollment ce ON ce.student_id = s.id
            WHERE ce.class_id = ? AND s.active = 1
            ORDER BY s.name
            """,
            (class_id,),
        )
    )


def class_enrolled_count(conn: sqlite3.Connection, class_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM class_enrollment WHERE class_id = ?", (class_id,)
    ).fetchone()
    return int(row["n"])


def list_sessions_by_date(
    conn: sqlite3.Connection, class_id: int, day: date
) -> list[sqlite3.Row]:
    """Return all sessions for a class on a given date, oldest first."""
    return list(
        conn.execute(
            "SELECT * FROM sessions WHERE class_id = ? AND date = ? ORDER BY id",
            (class_id, day.isoformat()),
        )
    )


def get_or_create_session(
    conn: sqlite3.Connection, class_id: int, day: date, label: str | None = None
) -> int:
    """Return the session id for a class on a given date, creating it if needed.

    When ``label`` is given, match that specific session (creating it if absent).
    Without a label, the earliest session for the date is returned (or one is
    created if the class has no session that day).
    """
    iso = day.isoformat()
    rows = conn.execute(
        "SELECT id, label FROM sessions WHERE class_id = ? AND date = ? ORDER BY id",
        (class_id, iso),
    ).fetchall()
    if label is not None:
        for r in rows:
            if r["label"] == label:
                return int(r["id"])
        cur = conn.execute(
            "INSERT INTO sessions (class_id, date, label) VALUES (?, ?, ?)",
            (class_id, iso, label),
        )
        return int(cur.lastrowid)
    if rows:
        return int(rows[0]["id"])
    cur = conn.execute(
        "INSERT INTO sessions (class_id, date) VALUES (?, ?)", (class_id, iso)
    )
    return int(cur.lastrowid)


def create_session(
    conn: sqlite3.Connection, class_id: int, day: date, label: str | None = None
) -> int:
    """Always insert a new session for a class on a date (used for multi-session days)."""
    cur = conn.execute(
        "INSERT INTO sessions (class_id, date, label) VALUES (?, ?, ?)",
        (class_id, day.isoformat(), label),
    )
    return int(cur.lastrowid)


def list_sessions(conn: sqlite3.Connection, class_id: int) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT * FROM sessions WHERE class_id = ? ORDER BY date DESC", (class_id,)
        )
    )


def set_session_photo(
    conn: sqlite3.Connection,
    session_id: int,
    filename: str,
    image_base64: str,
) -> None:
    """Store the uploaded group image metadata for a session (audit record)."""
    import json

    metadata = json.dumps({"filename": filename, "image_base64": image_base64})
    conn.execute(
        "UPDATE sessions SET photo = ? WHERE id = ?", (metadata, session_id)
    )


def get_session_photo(
    conn: sqlite3.Connection, session_id: int
) -> dict[str, str] | None:
    """Return the {filename, image_base64} metadata stored for a session."""
    import json

    row = conn.execute(
        "SELECT photo FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if row is None or not row["photo"]:
        return None
    return json.loads(row["photo"])


# --------------------------------------------------------------------------- #
# Attendance
# --------------------------------------------------------------------------- #


def mark_present(
    conn: sqlite3.Connection,
    session_id: int,
    student_id: int,
    distance: float | None = None,
    confidence: float | None = None,
    source: str | None = None,
) -> bool:
    """Mark a student present for a session. Returns False if already marked."""
    row = conn.execute(
        "SELECT id FROM attendance WHERE session_id = ? AND student_id = ?",
        (session_id, student_id),
    ).fetchone()
    if row is not None:
        return False
    conn.execute(
        """
        INSERT INTO attendance (session_id, student_id, status, distance, confidence, source)
        VALUES (?, ?, 'present', ?, ?, ?)
        """,
        (session_id, student_id, distance, confidence, source),
    )
    return True


def get_session_attendance(
    conn: sqlite3.Connection, session_id: int
) -> list[sqlite3.Row]:
    """Return attendance rows for a session joined with student names."""
    return list(
        conn.execute(
            """
            SELECT s.name, a.status, a.distance, a.confidence, a.source, a.marked_at
            FROM attendance a
            JOIN students s ON s.id = a.student_id
            WHERE a.session_id = ?
            ORDER BY s.name
            """,
            (session_id,),
        )
    )


def get_attendance_summary(
    conn: sqlite3.Connection,
    session_id: int,
    total_students: int,
    class_id: int | None = None,
) -> tuple[int, float]:
    """Return (present, progress) for a session.

    When the session's class has a declared enrollment (ground truth), ``present``
    counts only currently-enrolled students, so it can never exceed the enrolled
    roster even if attendance rows exist for students removed from the class.
    ``progress`` is clamped to [0, 1].
    """
    if class_id is not None and class_enrolled_count(conn, class_id) > 0:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM attendance a
            JOIN class_enrollment ce
              ON ce.class_id = ? AND ce.student_id = a.student_id
            WHERE a.session_id = ?
            """,
            (class_id, session_id),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM attendance WHERE session_id = ?", (session_id,)
        ).fetchone()
    present = int(row["n"])
    if total_students and present > total_students:
        present = total_students
    progress = (present / total_students) if total_students else 0.0
    return present, progress


def export_attendance_csv(
    conn: sqlite3.Connection,
    class_id: int,
    day: date,
) -> tuple[str, bytes]:
    """Produce a CSV (bytes) of all active students with present flags for a day."""
    import io

    session_id = get_or_create_session(conn, class_id, day)
    present_ids = {
        r["student_id"]
        for r in conn.execute(
            "SELECT student_id FROM attendance WHERE session_id = ?", (session_id,)
        )
    }
    if class_enrolled_count(conn, class_id) > 0:
        student_rows = enrolled_students(conn, class_id)
    else:
        student_rows = list_students(conn)
    rows = [
        {"Name": r["name"], "Gender": r["gender"], "Photo": r["photo"], "Present": int(r["id"] in present_ids)}
        for r in student_rows
    ]
    header = "Name,Gender,Photo,Present\n"
    body = "".join(
        f"{row['Name']},{row['Gender'] or ''},{row['Photo'] or ''},{row['Present']}\n"
        for row in rows
    )
    return f"attendance_{day.isoformat()}.csv", (header + body).encode("utf-8")


def export_session_attendance_csv(
    conn: sqlite3.Connection, session_id: int
) -> tuple[str, bytes]:
    """Produce a CSV of all active students with present flags for one session."""
    import io

    session = conn.execute(
        "SELECT * FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if session is None:
        return "attendance.csv", b""
    class_id = int(session["class_id"])
    day = session["date"]
    label = session["label"] or "session"

    present_ids = {
        r["student_id"]
        for r in conn.execute(
            "SELECT student_id FROM attendance WHERE session_id = ?", (session_id,)
        )
    }
    if class_enrolled_count(conn, class_id) > 0:
        student_rows = enrolled_students(conn, class_id)
    else:
        student_rows = list_students(conn)
    rows = [
        {"Name": r["name"], "Gender": r["gender"], "Photo": r["photo"], "Present": int(r["id"] in present_ids)}
        for r in student_rows
    ]
    header = "Name,Gender,Photo,Present\n"
    body = "".join(
        f"{row['Name']},{row['Gender'] or ''},{row['Photo'] or ''},{row['Present']}\n"
        for row in rows
    )
    return f"attendance_{day}_{label}.csv", (header + body).encode("utf-8")


# --------------------------------------------------------------------------- #
# Roster (one column per class/session) + CSV export
# --------------------------------------------------------------------------- #


def _session_columns(conn: sqlite3.Connection, class_id: int | None) -> list[sqlite3.Row]:
    query = """
        SELECT s.id, s.date, c.name AS class_name
        FROM sessions s
        JOIN classes c ON c.id = s.class_id
    """
    params: tuple = ()
    if class_id is not None:
        query += " WHERE s.class_id = ?"
        params = (class_id,)
    query += " ORDER BY s.date"
    return list(conn.execute(query, params))


def build_roster(
    conn: sqlite3.Connection, class_id: int | None = None
) -> tuple[list[dict[str, Any]], list[str]]:
    """Return (rows, class_columns).

    Each row is one student with one column per class/session (labelled
    ``"{ClassName} ({date})"``) plus an ``image_metadata`` column containing the
    stored filename/base64 payload. Attendance is sourced from the normalized
    ``attendance`` table.
    """
    sessions = _session_columns(conn, class_id)
    columns = [f"{s['class_name']} ({s['date']})" for s in sessions]

    if class_id is not None:
        students = enrolled_students(conn, class_id)
    else:
        students = list_students(conn)

    rows: list[dict[str, Any]] = []
    for student in students:
        row: dict[str, Any] = {
            "Name": student["name"],
            "Photo": student["photo"],
            "image_metadata": student["image_metadata"],
        }
        for session in sessions:
            record = conn.execute(
                "SELECT status FROM attendance WHERE session_id = ? AND student_id = ?",
                (session["id"], student["id"]),
            ).fetchone()
            row[f"{session['class_name']} ({session['date']})"] = (
                record["status"] if record else ""
            )
        rows.append(row)
    return rows, columns


def export_roster_csv(
    conn: sqlite3.Connection, class_id: int | None = None
) -> tuple[str, bytes]:
    """Export the pivoted roster (one column per class/session) as CSV bytes."""
    import io
    import json

    rows, columns = build_roster(conn, class_id)

    def cell(value: Any) -> str:
        if value is None:
            return ""
        text = str(value)
        return f'"{text}"' if any(ch in text for ch in '",\n') else text

    header = ["Name", "Photo", "image_metadata"] + columns
    lines = [",".join(cell(h) for h in header)]
    for row in rows:
        meta = json.loads(row["image_metadata"]) if row["image_metadata"] else ""
        meta_cell = meta.get("image_base64", "") if isinstance(meta, dict) else ""
        values = [row["Name"], row["Photo"], meta_cell] + [row[c] for c in columns]
        lines.append(",".join(cell(v) for v in values))

    buffer = io.StringIO("\n".join(lines))
    return "roster.csv", buffer.getvalue().encode("utf-8")


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #


def class_attendance_report(
    conn: sqlite3.Connection,
    class_id: int,
    start_date: date,
    end_date: date,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Return (rows, date_columns) matrix of per-student attendance over a range.

    Each row is one student with one ``YYYY-MM-DD`` column per session date in
    range (value ``present``/``absent``) plus an ``Attendance %`` summary.
    Falls back to all students when the class has no declared enrollment.
    """
    sessions = list(
        conn.execute(
            """
            SELECT id, date, label FROM sessions
            WHERE class_id = ? AND date BETWEEN ? AND ?
            ORDER BY date, id
            """,
            (class_id, start_date.isoformat(), end_date.isoformat()),
        )
    )
    dates = [
        s["date"] if not s["label"] else f"{s['date']} ({s['label']})"
        for s in sessions
    ]
    students = (
        enrolled_students(conn, class_id)
        if class_enrolled_count(conn, class_id) > 0
        else list_students(conn)
    )

    rows: list[dict[str, Any]] = []
    for student in students:
        row: dict[str, Any] = {
            "Name": student["name"],
            "Gender": student["gender"] or "",
        }
        present = 0
        for session, col in zip(sessions, dates):
            record = conn.execute(
                "SELECT status FROM attendance WHERE session_id = ? AND student_id = ?",
                (session["id"], student["id"]),
            ).fetchone()
            status = record["status"] if record else "absent"
            row[col] = status
            if status == "present":
                present += 1
        total = len(sessions)
        row["Attendance %"] = f"{round(present / total * 100)}%" if total else "-"
        rows.append(row)
    return rows, dates


def export_class_attendance_csv(
    conn: sqlite3.Connection,
    class_id: int,
    start_date: date,
    end_date: date,
) -> tuple[str, bytes]:
    """Export the class attendance matrix over a date range as CSV bytes."""
    import io

    rows, dates = class_attendance_report(conn, class_id, start_date, end_date)
    header = ["Name", "Gender"] + dates + ["Attendance %"]
    lines = [",".join(header)]
    for row in rows:
        lines.append(",".join(str(row[h]) for h in header))
    buffer = io.StringIO("\n".join(lines))
    filename = (
        f"class_{class_id}_attendance_{start_date.isoformat()}_{end_date.isoformat()}.csv"
    )
    return filename, buffer.getvalue().encode("utf-8")


def student_attendance_report(
    conn: sqlite3.Connection, student_id: int
) -> list[sqlite3.Row]:
    """Return per-session attendance rows for a student across their classes.

    Sessions are restricted to the classes the student is enrolled in, so a
    missing record means the student was absent for that session.
    """
    return list(
        conn.execute(
            """
            SELECT c.name AS class_name, s.date, a.status, a.source, a.marked_at
            FROM sessions s
            JOIN classes c ON c.id = s.class_id
            JOIN class_enrollment ce ON ce.class_id = c.id AND ce.student_id = ?
            LEFT JOIN attendance a ON a.session_id = s.id AND a.student_id = ?
            ORDER BY s.date DESC
            """,
            (student_id, student_id),
        )
    )


def export_student_attendance_csv(
    conn: sqlite3.Connection, student_id: int
) -> tuple[str, bytes]:
    """Export a student's per-session attendance record as CSV bytes."""
    import io

    rows = student_attendance_report(conn, student_id)
    header = ["Class", "Date", "Status", "Source", "Marked At"]
    lines = [",".join(header)]
    for r in rows:
        lines.append(
            ",".join(
                [
                    str(r["class_name"]),
                    str(r["date"]),
                    str(r["status"] or "absent"),
                    str(r["source"] or ""),
                    str(r["marked_at"] or ""),
                ]
            )
        )
    buffer = io.StringIO("\n".join(lines))
    return f"student_{student_id}_attendance.csv", buffer.getvalue().encode("utf-8")
