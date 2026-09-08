"""FastAPI service — thin adapter over the existing AttendanceService / recognition / repository."""

from __future__ import annotations

import base64
import io
import sys
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

# Make sure parent package is importable when running from the api/ dir
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from attendance import AttendanceService
from database import connect
import repository as repo
import recognition

# ---------------------------------------------------------------------------
# App + CORS
# ---------------------------------------------------------------------------

app = FastAPI(title="Attendance Tracker API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Service singleton
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "attendance.db"
PHOTOS_DIR = BASE_DIR / "photos"

svc = AttendanceService(db_path=DB_PATH, photos_dir=PHOTOS_DIR)
svc.init()

DEFAULT_THRESHOLD = 0.48


def _row_to_dict(row) -> dict:
    if row is None:
        return {}
    return dict(row)


# ---------------------------------------------------------------------------
# Classes
# ---------------------------------------------------------------------------


@app.get("/api/classes")
def list_classes():
    rows = svc.list_classes()
    result = []
    for r in rows:
        d = _row_to_dict(r)
        with connect(DB_PATH) as conn:
            d["enrolled_count"] = repo.class_enrolled_count(conn, d["id"])
        result.append(d)
    return result


@app.post("/api/classes", status_code=201)
def create_class(
    name: str = Form(...),
    subject: str = Form(""),
    batch_year: str = Form(""),
    student_count: int | None = Form(None),
):
    class_id = svc.add_class(name, subject, student_count, batch_year)
    cls = svc.get_class(class_id)
    return _row_to_dict(cls)


@app.get("/api/classes/{class_id}")
def get_class(class_id: int):
    cls = svc.get_class(class_id)
    if cls is None:
        raise HTTPException(404, "Class not found")
    d = _row_to_dict(cls)
    with connect(DB_PATH) as conn:
        d["enrolled_count"] = repo.class_enrolled_count(conn, class_id)
    return d


@app.get("/api/classes/{class_id}/students")
def get_class_students(class_id: int):
    students = svc.enrolled_students(class_id)
    result = []
    for s in students:
        d = _row_to_dict(s)
        d.pop("image_metadata", None)
        result.append(d)
    return result


@app.post("/api/classes/{class_id}/students")
def enroll_students(class_id: int, student_ids: list[int]):
    # FastAPI reads list[int] as JSON body
    with connect(DB_PATH) as conn:
        existing = repo.enrolled_student_ids(conn, class_id)
        merged = sorted(existing | set(student_ids))
        repo.set_enrollment(conn, class_id, merged)
    return {"enrolled": merged}



@app.delete("/api/classes/{class_id}/students/{student_id}")
def remove_from_class(class_id: int, student_id: int):
    with connect(DB_PATH) as conn:
        existing = repo.enrolled_student_ids(conn, class_id)
        existing.discard(student_id)
        repo.set_enrollment(conn, class_id, sorted(existing))
    return {"ok": True}


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------


@app.get("/api/students")
def list_students(include_image: bool = Query(False)):
    rows = svc.students()
    result = []
    for r in rows:
        d = _row_to_dict(r)
        if not include_image:
            d.pop("image_metadata", None)
        else:
            # Flatten image_metadata → image_b64 for convenience
            import json
            meta = d.pop("image_metadata", None)
            if meta:
                try:
                    parsed = json.loads(meta)
                    d["image_b64"] = parsed.get("image_base64")
                except Exception:
                    d["image_b64"] = None
            else:
                d["image_b64"] = None
        result.append(d)
    return result


@app.get("/api/students/{student_id}")
def get_student(student_id: int, include_image: bool = Query(True)):
    import json
    with connect(DB_PATH) as conn:
        row = repo.get_student(conn, student_id)
    if row is None:
        raise HTTPException(404, "Student not found")
    d = _row_to_dict(row)
    meta = d.pop("image_metadata", None)
    if include_image and meta:
        try:
            parsed = json.loads(meta)
            d["image_b64"] = parsed.get("image_base64")
        except Exception:
            d["image_b64"] = None
    else:
        d["image_b64"] = None
    return d


@app.post("/api/students", status_code=201)
async def register_student(
    name: str = Form(...),
    gender: str = Form(""),
    file: UploadFile = File(...),
):
    image_bytes = await file.read()
    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    filename = file.filename or f"{name}.jpg"
    student_id = svc.register_student(name, filename, image_b64, gender or None)
    # Embed the face
    try:
        svc.embed_student_from_db(student_id)
    except Exception as e:
        # Return partial success — student created, embedding failed
        return {"id": student_id, "name": name, "warning": str(e)}
    return {"id": student_id, "name": name}


@app.post("/api/students/register-crop", status_code=201)
async def register_from_crop(
    name: str = Form(...),
    gender: str = Form(""),
    class_id: int | None = Form(None),
    session_id: int | None = Form(None),
    crop_b64: str = Form(...),
    embedding_b64: str = Form(""),
):
    crop_bytes = base64.b64decode(crop_b64)
    from PIL import Image
    from io import BytesIO
    img = Image.open(BytesIO(crop_bytes)).convert("RGB")
    crop_rgb = np.array(img)

    embedding = None
    if embedding_b64:
        emb_bytes = base64.b64decode(embedding_b64)
        embedding = np.frombuffer(emb_bytes, dtype=np.float32)

    student_id = svc.register_student_from_crop(
        class_id=class_id,
        crop_rgb=crop_rgb,
        name=name,
        gender=gender or None,
        embedding=embedding,
    )

    # Optionally mark present for a specific session
    if session_id is not None:
        with connect(DB_PATH) as conn:
            repo.mark_present(conn, session_id, student_id, None, None, "manual")

    return {"id": student_id, "name": name}


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


@app.get("/api/sessions")
def list_sessions(
    class_id: int = Query(...),
    day: str | None = Query(None),
):
    if day:
        sessions = svc.sessions_for_date(class_id, date.fromisoformat(day))
    else:
        sessions = svc.list_sessions(class_id)
    return [_row_to_dict(s) for s in sessions]


@app.post("/api/sessions", status_code=201)
def create_session(
    class_id: int = Form(...),
    day: str = Form(...),
    label: str | None = Form(None),
):
    session_id = svc.create_session(class_id, date.fromisoformat(day), label or None)
    with connect(DB_PATH) as conn:
        row = repo.get_session(conn, session_id)
    return _row_to_dict(row)


# ---------------------------------------------------------------------------
# Attendance — analyze (preview, no DB write) + apply
# ---------------------------------------------------------------------------


@app.post("/api/attendance/analyze")
async def analyze_attendance(
    session_id: int = Form(...),
    threshold: float = Form(DEFAULT_THRESHOLD),
    scope: str = Form("class"),  # "class" | "all"
    file: UploadFile = File(...),
):
    image_bytes = await file.read()

    with connect(DB_PATH) as conn:
        session_row = repo.get_session(conn, session_id)
        if session_row is None:
            raise HTTPException(404, "Session not found")
        class_id = int(session_row["class_id"])

        scope_class_id = class_id if scope == "class" else None
        encoder = svc.get_encoder()
        encodings = svc._encodings_for_scope(conn, encoder, scope_class_id)

    candidates = recognition.preview_group_photo(image_bytes, encoder, encodings, threshold)

    # Store the image on the session for audit
    img_b64 = base64.b64encode(image_bytes).decode("ascii")
    filename = file.filename or "capture.jpg"
    with connect(DB_PATH) as conn:
        repo.set_session_photo(conn, session_id, filename, img_b64)

    recognized = [c for c in candidates if c["recognized"]]
    unknown = [c for c in candidates if not c["recognized"]]

    return {
        "recognized": [
            {
                "student_id": c["student_id"],
                "name": c["name"],
                "confidence": c["confidence"],
                "distance": c["distance"],
                "crop_b64": c["crop_b64"],
            }
            for c in recognized
        ],
        "unknown": [
            {
                "crop_b64": c["crop_b64"],
                "embedding_b64": c["embedding_b64"],
                "confidence": c["confidence"],
            }
            for c in unknown
        ],
        "total_faces": len(candidates),
    }


class ApplyBody(BaseModel):
    session_id: int
    student_ids: list[int]


@app.post("/api/attendance/apply")
def apply_attendance(body: ApplyBody):
    with connect(DB_PATH) as conn:
        for sid in body.student_ids:
            repo.mark_present(conn, body.session_id, sid, None, None, "confirmed")
    return {"marked": len(body.student_ids)}


@app.get("/api/attendance")
def get_attendance(session_id: int = Query(...)):
    rows = svc.session_attendance(session_id)
    return [_row_to_dict(r) for r in rows]


@app.get("/api/attendance/summary")
def get_attendance_summary(session_id: int = Query(...)):
    present, progress = svc.summary(session_id)
    total = svc.session_total(session_id)
    return {"present": present, "total": total, "progress": round(progress, 3)}


@app.post("/api/attendance/toggle")
def toggle_attendance(session_id: int, student_id: int):
    with connect(DB_PATH) as conn:
        new_status = repo.toggle_attendance(conn, session_id, student_id)
    return {"status": new_status}


@app.get("/api/attendance/export")
def export_attendance_csv(session_id: int = Query(...)):
    filename, data = svc.export_session_csv(session_id)
    return Response(
        content=data,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


@app.get("/api/reports/class")
def class_report(
    class_id: int = Query(...),
    from_date: str = Query(..., alias="from"),
    to_date: str = Query(..., alias="to"),
    export: bool = Query(False),
):
    start = date.fromisoformat(from_date)
    end = date.fromisoformat(to_date)
    if export:
        filename, data = svc.export_class_attendance(class_id, start, end)
        return Response(
            content=data,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    rows, columns = svc.class_attendance_report(class_id, start, end)
    return {"rows": rows, "columns": columns}


@app.get("/api/reports/student")
def student_report(
    student_id: int = Query(...),
    export: bool = Query(False),
):
    if export:
        filename, data = svc.export_student_attendance(student_id)
        return Response(
            content=data,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    rows = svc.student_attendance_report(student_id)
    return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Student image
# ---------------------------------------------------------------------------


@app.get("/api/students/{student_id}/photo")
def get_student_photo(student_id: int):
    import json
    with connect(DB_PATH) as conn:
        meta = repo.get_student_image(conn, student_id)
    if not meta or not meta.get("image_base64"):
        raise HTTPException(404, "No photo")
    img_bytes = base64.b64decode(meta["image_base64"])
    return Response(content=img_bytes, media_type="image/jpeg")


# ---------------------------------------------------------------------------
# Entry point (dev)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
