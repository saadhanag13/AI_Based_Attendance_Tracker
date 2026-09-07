"""Application-facing service facade.

Wraps the database repository and the recognition service behind one object the
Streamlit UI can call. Keeps the UI thin and gives a single place to manage
configuration (DB path, photos dir, active model).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np

from database import connect, init_db
from models import FaceEncoder, MODEL_NAME
from models.insightface_encoder import shared_analyzer
import recognition
import repository as repo


class AttendanceService:
    def __init__(
        self,
        db_path: Path | str,
        photos_dir: Path | str,
        model_name: str = MODEL_NAME,
    ) -> None:
        self.db_path = Path(db_path)
        self.photos_dir = Path(photos_dir)
        self.model_name = model_name

    # -- lifecycle -----------------------------------------------------------

    def init(self) -> None:
        init_db(self.db_path)

    def get_encoder(self) -> FaceEncoder:
        return shared_analyzer()

    # -- students ------------------------------------------------------------

    def register_students(self, rows: list[tuple[str, str]]) -> dict[str, int]:
        """Scan photos and persist encodings. ``rows`` is [(name, photo), ...]."""
        encoder = self.get_encoder()
        with connect(self.db_path) as conn:
            return recognition.register_students_from_photos(
                conn, self.photos_dir, encoder, rows
            )

    def register_student(
        self, name: str, filename: str, image_base64: str, gender: str | None = None
    ) -> int:
        """Upsert a student by name and store their uploaded image as base64."""
        with connect(self.db_path) as conn:
            student_id = repo.upsert_student(conn, name, filename, gender)
            repo.set_student_image(conn, student_id, filename, image_base64)
            return student_id

    def register_students_for_class(
        self, class_id: int, records: list[tuple[str, str, str]]
    ) -> dict[str, int]:
        """Register students (name, gender, photo_source) and enroll them in a class.

        Each photo source may be a URL or a filename resolved against the photos
        directory. New students get a face encoding computed from the photo.
        """
        encoder = self.get_encoder()
        student_ids: list[int] = []
        with connect(self.db_path) as conn:
            mapping = recognition.register_students_from_sources(
                conn, self.photos_dir, encoder, records
            )
            student_ids = list(mapping.values())
            repo.set_enrollment(conn, class_id, student_ids)
        return mapping

    def student_count(self) -> int:
        with connect(self.db_path) as conn:
            return repo.count_students(conn)

    def students(self) -> list:
        with connect(self.db_path) as conn:
            return repo.list_students(conn)

    def set_student_image(
        self, student_id: int, filename: str, image_base64: str
    ) -> None:
        with connect(self.db_path) as conn:
            repo.set_student_image(conn, student_id, filename, image_base64)

    def get_student_image(self, student_id: int) -> dict | None:
        with connect(self.db_path) as conn:
            return repo.get_student_image(conn, student_id)

    def embed_student_from_db(self, student_id: int) -> int:
        with connect(self.db_path) as conn:
            return recognition.embed_student_from_db(conn, self.get_encoder(), student_id)

    # -- roster ---------------------------------------------------------------

    def roster(self, class_id: int | None = None) -> tuple[list[dict], list[str]]:
        with connect(self.db_path) as conn:
            return repo.build_roster(conn, class_id)

    def roster_csv(self, class_id: int | None = None) -> tuple[str, bytes]:
        with connect(self.db_path) as conn:
            return repo.export_roster_csv(conn, class_id)

    # -- classes / sessions ---------------------------------------------------

    def list_classes(self) -> list:
        with connect(self.db_path) as conn:
            return repo.list_classes(conn)

    def get_class(self, class_id: int):
        with connect(self.db_path) as conn:
            return repo.get_class(conn, class_id)

    def add_class(
        self,
        name: str,
        subject: str = "",
        student_count: int | None = None,
        batch_year: str = "",
        student_ids: list[int] | None = None,
    ) -> int:
        with connect(self.db_path) as conn:
            class_id = repo.create_class(
                conn, name, subject, student_count, batch_year
            )
            if student_ids:
                repo.set_enrollment(conn, class_id, student_ids)
            return class_id

    def set_enrollment(self, class_id: int, student_ids: list[int]) -> None:
        with connect(self.db_path) as conn:
            repo.set_enrollment(conn, class_id, student_ids)

    def enrolled_students(self, class_id: int) -> list:
        with connect(self.db_path) as conn:
            return repo.enrolled_students(conn, class_id)

    def class_student_count(self, class_id: int) -> int:
        with connect(self.db_path) as conn:
            return repo.class_enrolled_count(conn, class_id)

    def get_session(
        self, class_id: int, day: date | None = None, label: str | None = None
    ) -> int:
        with connect(self.db_path) as conn:
            return repo.get_or_create_session(conn, class_id, day or date.today(), label)

    def sessions_for_date(self, class_id: int, day: date) -> list:
        with connect(self.db_path) as conn:
            return repo.list_sessions_by_date(conn, class_id, day)

    def create_session(
        self, class_id: int, day: date | None = None, label: str | None = None
    ) -> int:
        with connect(self.db_path) as conn:
            return repo.create_session(conn, class_id, day or date.today(), label)

    def list_sessions(self, class_id: int) -> list:
        with connect(self.db_path) as conn:
            return repo.list_sessions(conn, class_id)

    # -- attendance ------------------------------------------------------------

    def _encodings_for_session(self, conn, session_id: int) -> list[dict]:
        """Encodings scoped to a session's class enrollment (ground truth).

        Falls back to all students when the class has no enrollment defined, so
        legacy classes keep working.
        """
        row = conn.execute(
            "SELECT class_id FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is not None and repo.class_enrolled_count(conn, row["class_id"]) > 0:
            return repo.get_enrolled_encodings(conn, row["class_id"], self.model_name)
        return recognition.load_encodings(conn, self.get_encoder())

    def encodings(self) -> list[dict]:
        with connect(self.db_path) as conn:
            return recognition.load_encodings(conn, self.get_encoder())

    def recognize_and_mark(
        self,
        session_id: int,
        image_bytes: bytes,
        threshold: float,
        source: str = "image",
    ) -> recognition.MarkResult:
        encoder = self.get_encoder()
        with connect(self.db_path) as conn:
            encodings = self._encodings_for_session(conn, session_id)
            return recognition.mark_from_image(
                conn,
                session_id,
                image_bytes,
                encoder,
                encodings,
                threshold,
                source=source,
            )

    def analyze_and_mark_many(
        self,
        session_id: int,
        image_bytes: bytes,
        threshold: float,
        filename: str | None = None,
        source: str = "image",
        scope_class_id: int | None = None,
    ) -> tuple[list[recognition.FaceCandidate], list[recognition.MarkResult]]:
        """Analyze every face in an uploaded group photo.

        ``scope_class_id`` controls which encodings are matched against:
        ``None`` matches against all registered students, otherwise only the
        students enrolled in that class are considered. Known students are marked
        present; every face (including unrecognized ones) is returned as a
        :class:`FaceCandidate` with a cropped image so the UI can register new
        persons. The uploaded image is also stored on the session for
        audit/reporting.
        """
        import base64

        encoder = self.get_encoder()
        with connect(self.db_path) as conn:
            encodings = self._encodings_for_scope(conn, encoder, scope_class_id)
            candidates, marks = recognition.analyze_group_photo(
                conn,
                session_id,
                image_bytes,
                encoder,
                encodings,
                threshold,
                source=source,
            )
            if filename:
                repo.set_session_photo(
                    conn,
                    session_id,
                    filename,
                    base64.b64encode(image_bytes).decode("ascii"),
                )
            return candidates, marks

    def _encodings_for_scope(
        self, conn, encoder: FaceEncoder, scope_class_id: int | None
    ) -> list[dict]:
        """Encodings to match against for a group-photo scope.

        ``None`` (all classes) returns every registered student; a specific class
        returns that class's enrolled encodings, falling back to all students if
        the class has no declared enrollment.
        """
        if scope_class_id is not None:
            encodings = repo.get_enrolled_encodings(
                conn, scope_class_id, self.model_name
            )
            if encodings:
                return encodings
        return recognition.load_encodings(conn, encoder)

    def register_student_from_crop(
        self,
        class_id: int | None,
        crop_rgb,
        name: str,
        gender: str | None = None,
        embedding=None,
    ) -> int:
        """Register a newly detected person (from a face crop).

        ``class_id`` is the class to enroll the new student into (and mark them
        present for today's session). Pass ``None`` to register the student
        globally without assigning them to a class. ``embedding`` may be the
        precomputed face embedding from the original group photo, reused to avoid
        re-detection on the crop.
        """
        encoder = self.get_encoder()
        with connect(self.db_path) as conn:
            student_id = recognition.register_student_from_crop(
                conn, encoder, name, crop_rgb, gender, embedding
            )
            if class_id is not None:
                ids = repo.enrolled_student_ids(conn, class_id)
                ids.add(student_id)
                repo.set_enrollment(conn, class_id, sorted(ids))
                session_id = repo.get_or_create_session(conn, class_id, date.today())
                repo.mark_present(conn, session_id, student_id, None, None, "image")
            return student_id

    def capture_and_recognize(
        self,
        session_id: int,
        threshold: float,
        source: str = "webcam",
    ) -> tuple[np.ndarray | None, list[recognition.RecognitionResult], list[recognition.MarkResult]]:
        """Capture one webcam frame, recognize every face, and mark them present.

        Returns ``(frame_rgb, results, marks)`` so the UI can show the live frame
        and per-student info. ``frame_rgb`` is None if the camera is unavailable.
        """
        import cv2

        encoder = self.get_encoder()
        cap = cv2.VideoCapture(0)
        try:
            ok, frame = cap.read()
        finally:
            cap.release()
        if not ok:
            return None, [], []
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        with connect(self.db_path) as conn:
            encodings = self._encodings_for_session(conn, session_id)
            results, marks = recognition.mark_faces(
                conn, session_id, frame_rgb, encoder, encodings, threshold, source=source
            )
        return frame_rgb, results, marks

    def session_attendance(self, session_id: int) -> list:
        with connect(self.db_path) as conn:
            return repo.get_session_attendance(conn, session_id)

    def _session_class_id(self, conn, session_id: int) -> int | None:
        row = conn.execute(
            "SELECT class_id FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return int(row["class_id"]) if row is not None else None

    def _session_total(self, conn, session_id: int) -> int:
        class_id = self._session_class_id(conn, session_id)
        total = repo.class_enrolled_count(conn, class_id) if class_id is not None else 0
        if total == 0:
            total = repo.count_students(conn)
        return total

    def session_total(self, session_id: int) -> int:
        with connect(self.db_path) as conn:
            return self._session_total(conn, session_id)

    def summary(self, session_id: int) -> tuple[int, float]:
        """Return (present, progress). Progress is measured against the class's
        enrolled roster (ground truth); falls back to all students if the class
        has no enrollment defined."""
        with connect(self.db_path) as conn:
            class_id = self._session_class_id(conn, session_id)
            total = self._session_total(conn, session_id)
            return repo.get_attendance_summary(conn, session_id, total, class_id)

    def export_csv(self, class_id: int, day: date) -> tuple[str, bytes]:
        with connect(self.db_path) as conn:
            return repo.export_attendance_csv(conn, class_id, day)

    def export_session_csv(self, session_id: int) -> tuple[str, bytes]:
        with connect(self.db_path) as conn:
            return repo.export_session_attendance_csv(conn, session_id)

    # -- reports ---------------------------------------------------------------

    def class_attendance_report(
        self, class_id: int, start_date: date, end_date: date
    ) -> tuple[list[dict], list[str]]:
        with connect(self.db_path) as conn:
            return repo.class_attendance_report(conn, class_id, start_date, end_date)

    def export_class_attendance(
        self, class_id: int, start_date: date, end_date: date
    ) -> tuple[str, bytes]:
        with connect(self.db_path) as conn:
            return repo.export_class_attendance_csv(
                conn, class_id, start_date, end_date
            )

    def student_attendance_report(self, student_id: int) -> list:
        with connect(self.db_path) as conn:
            return repo.student_attendance_report(conn, student_id)

    def export_student_attendance(self, student_id: int) -> tuple[str, bytes]:
        with connect(self.db_path) as conn:
            return repo.export_student_attendance_csv(conn, student_id)

    def process_video(
        self,
        session_id: int,
        video_path: Path,
        threshold: float,
        frame_step: int = 15,
        on_frame=None,
    ) -> list[recognition.MarkResult]:
        encoder = self.get_encoder()
        encodings = self.encodings()
        with connect(self.db_path) as conn:
            return recognition.process_video(
                conn,
                session_id,
                video_path,
                encoder,
                encodings,
                threshold,
                frame_step=frame_step,
                on_frame=on_frame,
            )
