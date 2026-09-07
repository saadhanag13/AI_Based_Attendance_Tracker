"""Face recognition service.

Bridges the swappable model layer (:mod:`models`) with the repository. Handles
registering students from photos, recognizing a single image, and (for later
video support) processing frames from a video file.

Encodings are persisted in the database per model, so re-registering after a
model swap rebuilds them automatically.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Callable

import numpy as np
import sqlite3
from PIL import Image, UnidentifiedImageError

from database import connect, init_db
from models import DetectedFace, FaceEncoder, FaceModelError
from models.insightface_encoder import shared_analyzer
import repository as repo


class RecognitionError(Exception):
    """Raised for face registration or recognition failures."""


@dataclass(frozen=True)
class RecognitionResult:
    status: str  # recognized | no_face | multiple_faces | unknown
    name: str | None = None
    distance: float | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class MarkResult:
    """Outcome of attempting to mark a recognized student present."""

    status: str  # marked | already_marked | not_recognized
    name: str | None = None
    distance: float | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class FaceCandidate:
    """A single detected face with its match outcome and a cropped image.

    Used by the group-photo flow so the UI can show unrecognized faces and let
    the user register them as new students.
    """

    recognized: bool
    box: tuple[int, int, int, int]
    confidence: float
    crop: np.ndarray
    name: str | None = None
    distance: float | None = None
    embedding: np.ndarray | None = None


def _load_rgb(image: np.ndarray | bytes | Path) -> np.ndarray:
    """Convert various image inputs to a uint8 RGB numpy array."""
    if isinstance(image, (bytes, bytearray, memoryview)):
        try:
            with Image.open(BytesIO(bytes(image))) as img:
                return np.array(img.convert("RGB"))
        except UnidentifiedImageError as exc:
            raise RecognitionError("The provided file is not a valid image.") from exc
    if isinstance(image, (str, Path)):
        return _load_rgb(Path(image).read_bytes())
    return np.asarray(image)


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #


def register_students_from_photos(
    conn: sqlite3.Connection,
    photos_dir: Path,
    encoder: FaceEncoder,
    student_df_rows: list[tuple[str, str]],
) -> dict[str, int]:
    """Scan each (name, photo) pair, embed the single face, persist the encoding.

    ``student_df_rows`` is a list of ``(name, photo_filename)`` tuples.
    Returns a mapping of name -> student_id.
    """
    if not photos_dir.exists():
        raise RecognitionError(f"Photos folder not found: {photos_dir}")

    encoder.load()
    results: dict[str, int] = {}
    for name, photo_name in student_df_rows:
        name = name.strip()
        photo_name = photo_name.strip()
        if not name or not photo_name or photo_name.lower() == "nan":
            raise RecognitionError(f"Invalid photo filename for student: {name or '<blank>'}")
        student_id = _register_from_bytes(
            conn, encoder, name, photo_name, _load_rgb(photos_dir / photo_name)
        )
        results[name] = student_id
    return results


def register_students_from_sources(
    conn: sqlite3.Connection,
    photos_dir: Path,
    encoder: FaceEncoder,
    records: list[tuple[str, str, str]],
) -> dict[str, int]:
    """Register students from (name, gender, photo_source) rows.

    ``photo_source`` may be a URL (``http(s)://...``, fetched over the network)
    or a filename/path resolved against ``photos_dir``. Each photo is embedded,
    its base64 payload persisted, and the student stored with their gender.
    Returns a mapping of name -> student_id.
    """
    encoder.load()
    results: dict[str, int] = {}
    for name, gender, photo_source in records:
        name = name.strip()
        gender = (gender or "").strip()
        photo_source = (photo_source or "").strip()
        if not name or not photo_source or photo_source.lower() == "nan":
            raise RecognitionError(f"Invalid photo for student: {name or '<blank>'}")
        image_bytes = _resolve_photo(photo_source, photos_dir)
        rgb = _load_rgb(image_bytes)
        student_id = _register_from_bytes(conn, encoder, name, photo_source, rgb, gender)
        results[name] = student_id
    return results


def _resolve_photo(source: str, photos_dir: Path) -> bytes:
    """Return raw image bytes for a URL or a local path under ``photos_dir``."""
    lowered = source.lower()
    if lowered.startswith("http://") or lowered.startswith("https://"):
        import urllib.request

        try:
            with urllib.request.urlopen(source, timeout=20) as response:
                return response.read()
        except Exception as exc:  # pragma: no cover - network dependent
            raise RecognitionError(f"Unable to download photo from URL: {source}") from exc
    local = Path(source)
    if not local.is_absolute():
        local = photos_dir / source
    if not local.exists():
        raise RecognitionError(f"Photo file not found: {source}")
    return local.read_bytes()


def _register_from_bytes(
    conn: sqlite3.Connection,
    encoder: FaceEncoder,
    name: str,
    photo_source: str,
    rgb: np.ndarray,
    gender: str | None = None,
) -> int:
    """Embed a face from an RGB array and persist student + encoding + image."""
    faces = encoder.detect_and_embed(rgb)
    if not faces:
        raise RecognitionError(f"No detectable face found in photo: {photo_source}")
    if len(faces) > 1:
        raise RecognitionError(f"Multiple faces found in photo: {photo_source}")

    student_id = repo.upsert_student(conn, name, photo_source, gender)
    repo.save_encoding(conn, student_id, encoder.model_name(), faces[0].embedding)
    image_bytes = _rgb_to_bytes(rgb)
    filename = Path(photo_source).name or "photo.jpg"
    repo.set_student_image(
        conn, student_id, filename, base64.b64encode(image_bytes).decode("ascii")
    )
    return student_id


def _rgb_to_bytes(rgb: np.ndarray) -> bytes:
    """Encode an RGB numpy array to PNG bytes for persistence."""
    from io import BytesIO

    buffer = BytesIO()
    Image.fromarray(np.asarray(rgb, dtype=np.uint8)).save(buffer, format="PNG")
    return buffer.getvalue()


def _crop_face(rgb: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    """Extract a face crop from an RGB image, padded around the bounding box."""
    x1, y1, x2, y2 = box
    height, width = rgb.shape[:2]
    pad_x = int((x2 - x1) * 0.2)
    pad_y = int((y2 - y1) * 0.2)
    x1 = max(0, x1 - pad_x)
    y1 = max(0, y1 - pad_y)
    x2 = min(width, x2 + pad_x)
    y2 = min(height, y2 + pad_y)
    return np.asarray(rgb[y1:y2, x1:x2], dtype=np.uint8)


def embed_student_from_db(
    conn: sqlite3.Connection, encoder: FaceEncoder, student_id: int
) -> int:
    """Recompute and store a student's embedding from their stored base64 image.

    This lets the model layer refer to the persisted image payload directly
    (e.g. after a model swap) instead of re-reading the photo file.
    """
    meta = repo.get_student_image(conn, student_id)
    if not meta or not meta.get("image_base64"):
        raise RecognitionError(
            f"No stored image for student id {student_id}; register them first."
        )
    image_bytes = base64.b64decode(meta["image_base64"])
    rgb = _load_rgb(image_bytes)
    faces = encoder.detect_and_embed(rgb)
    if not faces:
        raise RecognitionError("No detectable face found in the stored image.")
    if len(faces) > 1:
        raise RecognitionError("Multiple faces found in the stored image.")
    repo.save_encoding(conn, student_id, encoder.model_name(), faces[0].embedding)
    return student_id


# --------------------------------------------------------------------------- #
# Recognition
# --------------------------------------------------------------------------- #


def _match(
    detected: DetectedFace, encodings: list[dict], threshold: float
) -> tuple[str | None, float]:
    """Return (name, distance) for the closest match under ``threshold``."""
    candidate = detected.embedding
    known_matrix = np.stack([e["embedding"] for e in encodings])
    similarities = known_matrix @ candidate
    distances = 1.0 - similarities
    best_index = int(np.argmin(distances))
    best_distance = float(distances[best_index])
    if best_distance <= threshold:
        return encodings[best_index]["name"], best_distance
    return None, best_distance


def recognize_image(
    conn: sqlite3.Connection,
    image: np.ndarray | bytes | Path,
    encoder: FaceEncoder,
    encodings: list[dict],
    threshold: float,
) -> RecognitionResult:
    """Recognize a student in a single image against a set of known encodings."""
    encoder.load()
    rgb = _load_rgb(image)
    faces = encoder.detect_and_embed(rgb)
    if not faces:
        return RecognitionResult(status="no_face")
    if len(faces) > 1:
        return RecognitionResult(status="multiple_faces")

    name, distance = _match(faces[0], encodings, threshold)
    if name is None:
        return RecognitionResult(status="unknown", distance=distance)
    return RecognitionResult(
        status="recognized",
        name=name,
        distance=distance,
        confidence=faces[0].confidence,
    )


def mark_from_image(
    conn: sqlite3.Connection,
    session_id: int,
    image: np.ndarray | bytes | Path,
    encoder: FaceEncoder,
    encodings: list[dict],
    threshold: float,
    source: str = "image",
) -> MarkResult:
    """Recognize a face in an image and mark it present for the session."""
    result = recognize_image(conn, image, encoder, encodings, threshold)
    if result.status != "recognized" or result.name is None:
        return MarkResult(status=result.status, distance=result.distance)

    name_to_id = {e["name"]: e["student_id"] for e in encodings}
    student_id = name_to_id[result.name]
    already = repo.mark_present(
        conn,
        session_id=session_id,
        student_id=student_id,
        distance=result.distance,
        confidence=result.confidence,
        source=source,
    )
    status = "marked" if already else "already_marked"
    return MarkResult(
        status=status,
        name=result.name,
        distance=result.distance,
        confidence=result.confidence,
    )


def mark_faces(
    conn: sqlite3.Connection,
    session_id: int,
    image: np.ndarray | bytes | Path,
    encoder: FaceEncoder,
    encodings: list[dict],
    threshold: float,
    source: str = "webcam",
) -> tuple[list[RecognitionResult], list[MarkResult]]:
    """Recognize every face in an image and mark each known student present.

    Used for live/group feeds where multiple students may appear in one frame.
    Returns ``(per_face_results, mark_results)`` so the UI can show student info
    and per-student tagging status.
    """
    encoder.load()
    rgb = _load_rgb(image)
    faces = encoder.detect_and_embed(rgb)
    name_to_id = {e["name"]: e["student_id"] for e in encodings}

    results: list[RecognitionResult] = []
    marks: list[MarkResult] = []
    for face in faces:
        name, distance = _match(face, encodings, threshold)
        if name is None:
            results.append(RecognitionResult(status="unknown", distance=distance))
            continue
        results.append(
            RecognitionResult(
                status="recognized", name=name, distance=distance, confidence=face.confidence
            )
        )
        already = repo.mark_present(
            conn,
            session_id=session_id,
            student_id=name_to_id[name],
            distance=distance,
            confidence=face.confidence,
            source=source,
        )
        marks.append(
            MarkResult(
                status="marked" if already else "already_marked",
                name=name,
                distance=distance,
                confidence=face.confidence,
            )
        )
    return results, marks


def analyze_group_photo(
    conn: sqlite3.Connection,
    session_id: int,
    image: np.ndarray | bytes | Path,
    encoder: FaceEncoder,
    encodings: list[dict],
    threshold: float,
    source: str = "image",
) -> tuple[list[FaceCandidate], list[MarkResult]]:
    """Analyze every face in a group photo: match + mark known students present.

    Returns ``(candidates, marks)``. Each candidate carries a cropped face image
    (and its match outcome) so the UI can register unrecognized faces as new
    students. Known faces are marked present for the session.
    """
    encoder.load()
    rgb = _load_rgb(image)
    faces = encoder.detect_and_embed(rgb)
    name_to_id = {e["name"]: e["student_id"] for e in encodings}

    candidates: list[FaceCandidate] = []
    marks: list[MarkResult] = []
    for face in faces:
        name, distance = _match(face, encodings, threshold)
        crop = _crop_face(rgb, face.box)
        recognized = name is not None
        candidates.append(
            FaceCandidate(
                recognized=recognized,
                box=face.box,
                confidence=face.confidence,
                crop=crop,
                name=name,
                distance=distance,
                embedding=face.embedding,
            )
        )
        if recognized:
            already = repo.mark_present(
                conn,
                session_id=session_id,
                student_id=name_to_id[name],
                distance=distance,
                confidence=face.confidence,
                source=source,
            )
            marks.append(
                MarkResult(
                    status="marked" if already else "already_marked",
                    name=name,
                    distance=distance,
                    confidence=face.confidence,
                )
            )
    return candidates, marks


def register_student_from_crop(
    conn: sqlite3.Connection,
    encoder: FaceEncoder,
    name: str,
    crop_rgb: np.ndarray,
    gender: str | None = None,
    embedding: np.ndarray | None = None,
) -> int:
    """Register a new student from a cropped face image.

    When ``embedding`` is supplied (e.g. precomputed from the original group
    photo) it is reused directly, avoiding a second detection pass that can fail
    on small crops. Otherwise the single face in the crop is detected. The
    student, its embedding and the crop (stored image) are persisted.
    """
    encoder.load()
    if embedding is None:
        faces = encoder.detect_and_embed(np.asarray(crop_rgb, dtype=np.uint8))
        if not faces:
            raise RecognitionError("No face detected in the selected photo.")
        if len(faces) > 1:
            raise RecognitionError("Multiple faces detected in the selected photo.")
        embedding = faces[0].embedding

    student_id = repo.upsert_student(conn, name, None, gender)
    repo.save_encoding(conn, student_id, encoder.model_name(), np.asarray(embedding))
    image_bytes = _rgb_to_bytes(np.asarray(crop_rgb, dtype=np.uint8))
    filename = f"{name}.jpg"
    repo.set_student_image(
        conn, student_id, filename, base64.b64encode(image_bytes).decode("ascii")
    )
    return student_id


# --------------------------------------------------------------------------- #
# Video (ready for later use)
# --------------------------------------------------------------------------- #


def process_video(
    conn: sqlite3.Connection,
    session_id: int,
    video_path: Path,
    encoder: FaceEncoder,
    encodings: list[dict],
    threshold: float,
    frame_step: int = 15,
    on_frame: Callable[[int, MarkResult], None] | None = None,
) -> list[MarkResult]:
    """Process a video file, marking each recognized student once.

    Iterates frames, runs recognition periodically, and stops marking a student
    once they have been recorded for the session. Designed to be wired into the
    UI or a batch job later.
    """
    import cv2

    encoder.load()
    present_names = {e["name"] for e in encodings}
    results: list[MarkResult] = []

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RecognitionError(f"Unable to open video: {video_path}")

    try:
        frame_index = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if frame_index % frame_step != 0:
                frame_index += 1
                continue
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = recognize_image(conn, frame_rgb, encoder, encodings, threshold)
            if result.status == "recognized" and result.name in present_names:
                mark = mark_from_image(
                    conn,
                    session_id,
                    frame_rgb,
                    encoder,
                    encodings,
                    threshold,
                    source="video",
                )
                results.append(mark)
                if on_frame is not None:
                    on_frame(frame_index, mark)
                if mark.status == "marked":
                    present_names.discard(mark.name)
                    if not present_names:
                        break
            frame_index += 1
    finally:
        cap.release()

    return results


# --------------------------------------------------------------------------- #
# Convenience helpers
# --------------------------------------------------------------------------- #


def load_encodings(conn: sqlite3.Connection, encoder: FaceEncoder) -> list[dict]:
    """Fetch stored encodings for the encoder's model from the database."""
    return repo.get_encodings(conn, encoder.model_name())


def get_shared_encoder() -> FaceEncoder:
    """Return the process-wide InsightFace encoder singleton."""
    return shared_analyzer()
