"""Read student rosters from CSV/Excel for seeding the database.

Attendance is stored in SQLite; this module only handles ingesting a roster
sheet (name + photo filename) the first time the app runs.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = {"Name", "Photo"}


class AttendanceDataError(Exception):
    """Raised when the student roster sheet is unavailable or invalid."""


def load_student_sheet(data_path: Path) -> pd.DataFrame:
    """Read a student roster from a CSV or Excel file."""
    if not data_path.exists():
        raise AttendanceDataError(f"Student data file not found: {data_path.name}")

    try:
        if data_path.suffix.lower() == ".csv":
            student_df = pd.read_csv(data_path)
        else:
            student_df = pd.read_excel(data_path)
    except Exception as exc:  # pragma: no cover - engine/runtime dependent
        raise AttendanceDataError(f"Unable to read student data file: {data_path.name}") from exc

    missing_columns = REQUIRED_COLUMNS.difference(student_df.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise AttendanceDataError(f"Student data file is missing required columns: {missing}")

    return student_df.copy()


def sheet_to_rows(student_df: pd.DataFrame) -> list[tuple[str, str]]:
    """Return [(name, photo_filename), ...] rows for registration."""
    rows: list[tuple[str, str]] = []
    for record in student_df.itertuples(index=False):
        rows.append((str(record.Name).strip(), str(record.Photo).strip()))
    return rows


CLASS_REQUIRED_COLUMNS = {"student_name", "gender", "photo"}


def load_class_csv(data_path: Path) -> pd.DataFrame:
    """Read a class student list: columns ``student_name``, ``gender``, ``photo``.

    ``photo`` is a URL (``http(s)://...``) or a filename/path resolvable against
    the photos directory. Returns a DataFrame copy.
    """
    if not data_path.exists():
        raise AttendanceDataError(f"Class student file not found: {data_path.name}")
    try:
        student_df = pd.read_csv(data_path)
    except Exception as exc:  # pragma: no cover - engine dependent
        raise AttendanceDataError(f"Unable to read class student file: {data_path.name}") from exc

    present = {c.strip().lower(): c for c in student_df.columns}
    missing = CLASS_REQUIRED_COLUMNS.difference(present)
    if missing:
        raise AttendanceDataError(
            f"Class student file must contain columns: {', '.join(sorted(CLASS_REQUIRED_COLUMNS))}"
        )
    rename = {v: k for k, v in present.items()}
    return student_df.rename(columns=rename)[list(CLASS_REQUIRED_COLUMNS)].copy()


def class_rows_to_records(student_df: pd.DataFrame) -> list[tuple[str, str, str]]:
    """Return [(student_name, gender, photo), ...] records for registration."""
    records: list[tuple[str, str, str]] = []
    for record in student_df.itertuples(index=False):
        records.append(
            (
                str(record.student_name).strip(),
                str(record.gender).strip(),
                str(record.photo).strip(),
            )
        )
    return records
