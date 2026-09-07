# Face Recognition Attendance System — Product Requirements Document

## 1. Overview

The **Face Recognition Attendance System** automates class attendance by detecting and
recognizing faces in a group photo (or a single captured frame). It matches detected faces
against students enrolled in the selected class (or all registered students), records
attendance for a chosen **class + date + session**, flags unrecognized faces so they can be
**registered as new students** on the spot, and provides reporting and export (CSV).

### Vision
"Modern attendance tracking": a teacher takes one photo of a class; the system does the
roll-call, handles new faces, and produces records and reports automatically.

### Scope
- Face-based attendance capture via **group-photo upload** and **browser camera capture**.
- Student and class registration, including registering new persons detected in a photo.
- Multi-session support (a class can have several sessions on the same date).
- Attendance review/confirmation and correction (mark/unmark).
- Reporting: class attendance matrix over a date range, and per-student history, with CSV export.

### Out of scope (Phase 1)
- Authentication / role-based access.
- PostgreSQL (keep SQLite; repository layer is isolated for a future swap).
- PDF/XLSX exports (CSV only for now; additive later).
- Live streaming continuous recognition (only single-frame capture / upload).

---

## 2. Personas & Goals

| Persona | Goals |
|---|---|
| **Admin** | Create classes, manage rosters, bulk-import students, generate reports. |
| **Teacher** | Quickly mark attendance from a photo, register new students found in photos, correct mistakes, download day records. |

---

## 3. Current State (existing backend to be reused)

The existing Python codebase is the service layer. It **must** remain Python because the face
model (InsightFace `buffalo_l`) is a Python/ONNX library loaded as a process singleton
(`models/insightface_encoder.py` → `shared_analyzer()`), which cannot run in the browser.

Key modules (reuse unchanged where possible):

| Module | Responsibility |
|---|---|
| `models/` | `FaceEncoder` interface + InsightFace `buffalo_l` encoder; swappable model layer. |
| `recognition.py` | Detection → embedding → cosine matching; group-photo analysis; crop registration. |
| `repository.py` | All SQL over SQLite (isolated data-access layer). |
| `database.py` | Schema + migrations (students, student_encodings, classes, class_enrollment, sessions, attendance). |
| `attendance.py` | `AttendanceService` facade the UI/API calls. |
| `app.py` | Current Streamlit UI (to be replaced by Next.js). |
| `excel_utils.py` | CSV/Excel roster ingestion. |

### Existing data model
- `students` — id, name, photo, gender, image_metadata (base64 image), active.
- `student_encodings` — per (student, model): embedding BLOB.
- `classes` — id, name, subject, student_count, batch_year.
- `class_enrollment` — ground-truth roster (class ↔ student).
- `sessions` — one class may have **multiple sessions per date** (label disambiguates); stores the uploaded group photo for audit.
- `attendance` — (session, student) present record with distance/confidence/source/marked_at; UNIQUE(session_id, student_id).

---

## 4. Architecture

```
Browser (Next.js frontend, App Router + TypeScript)
   │  REST / JSON (fetch or SWR/TanStack Query)
   ▼
FastAPI service (Python) — thin adapter over AttendanceService / recognition / repository
   │
   ▼
SQLite (attendance.db)  +  .insightface (model)  +  photos/
```

### Key decisions
- **Backend stays Python** (face model constraint). Frontend is **Next.js only**.
- **FastAPI** exposes the existing Python service layer as a REST API.
- **Keep SQLite** for now. All SQL lives in `repository.py`, so migrating to PostgreSQL later is a
  single-layer change.
- **Single uvicorn worker** (the model is a per-process singleton, ~100s MB RAM). If multiple
  workers are needed later, extract inference behind its own service.
- **Auth-ready seams** but no auth in MVP: dependency-injected `get_current_user` / `require_role`
  placeholders so roles (admin/teacher) can be added without rework.

---

## 5. Backend API (FastAPI)

### Endpoints

| Area | Method & Path | Purpose |
|---|---|---|
| Classes | `GET /api/classes` | List classes |
| | `POST /api/classes` | Create class |
| | `GET /api/classes/{id}` | Class detail |
| | `GET /api/classes/{id}/students` | Roster (enrolled students) |
| | `POST /api/classes/{id}/students` | Enroll students |
| Students | `GET /api/students` | List students |
| | `POST /api/students` | Register a student from an uploaded image |
| | `POST /api/students/register-crop` | Register a new person from a face crop (from group photo) |
| Sessions | `GET /api/sessions?class_id&date` | List sessions for a class+date |
| | `POST /api/sessions` | Create a session (with optional label) |
| Attendance | `POST /api/attendance/analyze` | Upload/capture image → detect+match → return candidates (crops as base64) + recognized marks. **No DB writes (preview).** |
| | `POST /api/attendance/apply` | Mark the confirmed set of students present for a session |
| | `GET /api/attendance?session_id` | Per-session records |
| | `GET /api/attendance/summary?session_id` | Present / total / progress |
| | `POST /api/attendance/{id}/toggle` | Correct/update a mark (mark/unmark) |
| Reports | `GET /api/reports/class?class_id&from&to` (+`&export=csv`) | Class attendance matrix |
| | `GET /api/reports/student?student_id` (+`&export=csv`) | Per-student history + summary |

### Preview → Apply flow (core UX)
The current backend marks-on-upload. For a richer "review → confirm" experience:

1. `POST /api/attendance/analyze` runs detection + matching, returns:
   - `recognized`: list of known students matched (with name, confidence).
   - `unknown`: list of unrecognized faces (with base64 **crop image** + precomputed embedding) for the register-new-person UI.
   - Nothing is written to the DB.
2. `POST /api/attendance/apply` marks the frontend-confirmed student ids present for the session.
3. `POST /api/students/register-crop` registers + enrolls any new person the user chose to add, and (optionally) marks them present.

### Backend gaps to close (small additions)
- `preview_analysis(...)` in `recognition.py` — detect + match + crops, **no** persistence (separate from `mark_faces`).
- `mark_student_present` / `unmark_student` / `toggle` in `repository.py` for correction.
- Return face crops as base64 JSON (frontend renders them directly; no server-side intermediate storage).

---

## 6. Frontend (Next.js)

### Structure
```
app/
  layout.tsx                     – global shell + nav (Dashboard / Attendance / Students / Classes / Reports)
  page.tsx                       – dashboard (today's classes, quick actions)
  attendance/[classId]/page.tsx  – core capture flow
  students/page.tsx              – list + register
  students/[id]/page.tsx         – profile + attendance history
  classes/page.tsx               – create class, manage roster, CSV import
  reports/page.tsx               – class matrix + student reports + exports
components/
  PhotoUploader.tsx    – file input + <canvas> camera capture (getUserMedia, single frame)
  FaceReviewCard.tsx   – unknown-face crop, Name/Gender/class inputs, Register/Skip
  AttendanceTable.tsx  – per-session records, toggle present/absent
  SessionPicker.tsx    – date + session list + "New session"
  ClassMatrix.tsx      – student × date report grid
lib/api.ts             – typed API client
lib/format.ts, lib/constants.ts
```

### Data fetching
- **SWR or TanStack Query** for cached lists + optimistic attendance updates.

### Camera capture
- `navigator.mediaDevices.getUserMedia` → draw one frame to `<canvas>` → `canvas.toBlob('image/jpeg')` → POST to `/api/attendance/analyze` (same path as upload). Show preview before confirming.

---

## 7. User Journey

### Setup (once, admin)
1. Create a **Class** (name, subject, batch).
2. **Register Students** — one-by-one photo or **CSV upload** → faces embedded and stored.
   (Or later: register new faces as they appear in group photos.)

### Class day (teacher)
1. Open **Attendance → select class → date → session** (or create a new session for the day).
2. **Upload a group photo** OR **capture a frame from the camera**.
3. System detects all faces and matches against the class roster (scope: *this class* or *all classes*).
4. **Review:**
   - Enrolled students detected → shown as present (confirm).
   - Unrecognized faces → flagged as **New Person**.
5. **New-person handling:** for each new face, enter Name/Gender and pick a target class →
   student is registered, embedded, enrolled, and (optionally) marked present.
6. **Confirm** → attendance recorded to the session.
7. Correct any mistakes (toggle present/absent). Download the day's CSV.

### Reporting
- **Class report:** student × date matrix over a date range (multi-session columns labelled),
  with an attendance % column → CSV.
- **Student report:** per-session history across their classes + summary → CSV.

---

## 8. Functional Requirements

### FR-1 Classes
- Create, list, view a class.
- Declare subject, batch year, student count (informational).
- Manage the enrolled roster (ground truth for attendance).

### FR-2 Students
- Register a student from an uploaded image (name, gender) → face embedded + image stored.
- Bulk-register via CSV (`student_name, gender, photo`).
- Register a new person from a face crop detected in a group photo.
- Re-embed a student's encoding after a photo update.

### FR-3 Sessions
- A class can have **multiple sessions on the same date**, distinguished by an optional label
  (e.g. Morning / Afternoon).
- Create a session for a chosen class + date.
- Store the uploaded group photo against the session for audit.

### FR-4 Attendance capture
- Analyze a group image: detect all faces, match against scoped encodings.
- Scope: **only this class** (enrolled students) or **all classes** (all registered students).
- Return recognized faces (with confidence) and unrecognized faces (with crops) **before persisting**.
- Apply confirmed attendance to a session.

### FR-5 Attendance update / correction
- View per-session attendance.
- Mark / unmark an individual student (correction).

### FR-6 Reports
- Class attendance matrix over a date range (columns labelled with session label when needed).
- Per-student attendance history + attendance %.
- CSV export for both.

### FR-7 Camera capture
- Capture a single frame from the browser camera and run it through the same analyze flow.

---

## 9. Non-Functional Requirements

- **Performance:** Face analysis is the bottleneck; preview should show a spinner. Model loaded
  once per process.
- **Concurrency:** Single worker recommended; SQLite writes serialized (acceptable for single school).
- **Data integrity:** attendance is UNIQUE per (session, student); corrections must respect that.
- **Extensibility:** model layer swappable (`FaceEncoder`); DB layer isolated in `repository.py`;
  auth deps as no-op placeholders.
- **Deployment:** Dockerizable (FastAPI service + Next.js container + shared `attendance.db`/model volume).

---

## 10. Implementation Plan

### Phase 1 — MVP
1. **Backend API:** add `api/` FastAPI package; `preview_analysis` / `apply` split; correction toggle.
2. **Frontend scaffold:** Next.js (App Router, TS, Tailwind) + typed API client + nav shell + `SessionPicker` + `PhotoUploader`.
3. **Attendance flow:** upload/capture → review → register new → confirm → records + CSV.
4. **Students & Classes:** registration (image + CSV), roster management, profile with history.
5. **Reports:** class matrix + student report + CSV exports.
6. **Dashboard:** today's sessions + quick actions.

### Phase 2 — Polish
- Student profile pages with history.
- Camera capture (if not in Phase 1).
- Attendance correction UX refinements.

### Phase 3 — Scale (future)
- Auth + roles (admin/teacher/student views).
- PostgreSQL migration (repository-only change).
- PDF/XLSX exports (additive).
- Multi-worker inference service if needed.

---

## 11. Open Decisions / Follow-ups

- [ ] Confirm MVP scope for camera capture (Phase 1 vs 2).
- [ ] Decide on auth timing (defer is fine; seams are in place).
- [ ] Decide hosting/deployment target (affects Docker setup).
- [ ] Confirm single-school SQLite vs planned multi-tenant.
