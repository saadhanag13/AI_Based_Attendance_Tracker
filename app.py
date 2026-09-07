from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from attendance import AttendanceService
from excel_utils import (
    AttendanceDataError,
    class_rows_to_records,
    load_class_csv,
    load_student_sheet,
    sheet_to_rows,
)
from recognition import RecognitionError


BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "attendance.db"
PHOTOS_DIR = BASE_DIR / "photos"
SEED_SHEET = BASE_DIR / "sample_students.csv"
DEFAULT_THRESHOLD = 0.48


def get_service() -> AttendanceService:
    """Return a service instance. Not cached: the model itself is cached as a
    process singleton in ``shared_analyzer``, and caching the wrapper here caused
    stale objects after code edits during a running session."""
    service = AttendanceService(db_path=DB_PATH, photos_dir=PHOTOS_DIR)
    service.init()
    return service


def seed_students_if_needed(service: AttendanceService) -> None:
    """Import the roster sheet and register face encodings on first run."""
    if service.student_count() > 0:
        return
    if not SEED_SHEET.exists():
        st.warning(f"Seed roster not found: {SEED_SHEET.name}. Add students to continue.")
        return
    try:
        sheet = load_student_sheet(SEED_SHEET)
    except AttendanceDataError as exc:
        st.error(str(exc))
        return
    with st.spinner("Registering student faces (first run)..."):
        try:
            service.register_students(sheet_to_rows(sheet))
        except RecognitionError as exc:
            st.error(str(exc))
            st.stop()


def render_class_selector(service: AttendanceService) -> int | None:
    classes = service.list_classes()
    names = [c["name"] for c in classes]
    if not names:
        st.info("No classes yet. Register a class on the Class Registration page.")
        return None
    selected = st.selectbox("Select class", names, key="class_name")
    return int(next(c["id"] for c in classes if c["name"] == selected))


def render_class_registration(service: AttendanceService) -> None:
    """Separate page to register a class record (ground truth for attendance)."""
    st.subheader("1. Register a class record")
    with st.form("class_registration_form"):
        name = st.text_input("Class name *", placeholder="e.g. 6-A")
        subject = st.text_input("Subject", placeholder="e.g. Mathematics")
        col1, col2 = st.columns(2)
        student_count = col1.number_input(
            "Student count", min_value=0, step=1, value=0
        )
        batch_year = col2.text_input("Batch year", placeholder="e.g. 2026")
        submitted = st.form_submit_button("Register class")

    if submitted:
        if not name.strip():
            st.error("Class name is required.")
        else:
            try:
                class_id = service.add_class(
                    name=name.strip(),
                    subject=subject.strip(),
                    student_count=int(student_count),
                    batch_year=batch_year.strip(),
                )
                st.session_state["selected_class_id"] = class_id
                st.success(f"Registered class '{name.strip()}' (id {class_id}).")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    st.subheader("2. Register students for a class")
    classes = service.list_classes()
    if not classes:
        st.info("No classes registered yet. Create one above.")
    else:
        names = [c["name"] for c in classes]
        sel = st.selectbox("Select class", names, key="reg_class")
        sel_id = int(next(c["id"] for c in classes if c["name"] == sel))
        st.session_state["selected_class_id"] = sel_id

        method = st.radio(
            "Registration method", ["One by one", "Upload CSV"], horizontal=True
        )
        if method == "One by one":
            _render_student_one_by_one(service, sel_id)
        else:
            _render_student_csv(service, sel_id)

        roster = service.enrolled_students(sel_id)
        st.write(f"**Enrolled roster ({len(roster)}):**")
        if roster:
            st.dataframe(
                pd.DataFrame(
                    [dict(r) for r in roster],
                    columns=[c for c in roster[0].keys()],
                ),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.caption("No students enrolled yet.")

    st.subheader("3. Existing classes")
    for cls in classes:
        enrolled_count = service.class_student_count(cls["id"])
        declared = cls["student_count"] or 0
        with st.expander(f"{cls['name']} — {cls['subject'] or 'no subject'}"):
            st.write(f"Batch year: {cls['batch_year'] or '—'}")
            st.write(f"Declared student count: {declared} | Enrolled: {enrolled_count}")
            roster = service.enrolled_students(cls["id"])
            roster_text = ", ".join(r["name"] for r in roster) if roster else "(none)"
            st.write(f"Enrolled roster: {roster_text}")


def _render_student_one_by_one(service: AttendanceService, class_id: int) -> None:
    col1, col2 = st.columns(2)
    name = col1.text_input("Student name", key="one_name")
    gender = col2.selectbox("Gender", ["", "Male", "Female", "Other"], key="one_gender")
    uploaded = st.file_uploader(
        "Student photo", type=["jpg", "jpeg", "png"], key="one_photo"
    )
    if st.button("Register and enroll", key="one_btn"):
        if not name.strip() or uploaded is None:
            st.error("Provide a name and a photo.")
        else:
            import base64

            image_base64 = base64.b64encode(uploaded.getvalue()).decode("ascii")
            try:
                student_id = service.register_student(
                    name.strip(), uploaded.name, image_base64, gender or None
                )
                service.embed_student_from_db(student_id)
                service.set_enrollment(
                    class_id,
                    [r["id"] for r in service.enrolled_students(class_id)]
                    + [student_id],
                )
                st.success(f"Enrolled {name.strip()} in the class.")
                st.rerun()
            except RecognitionError as exc:
                st.error(str(exc))


def _render_student_csv(service: AttendanceService, class_id: int) -> None:
    st.caption("CSV columns: `student_name`, `gender`, `photo` (URL or file path).")
    uploaded = st.file_uploader(
        "Class student CSV", type=["csv"], key="class_csv"
    )
    if uploaded is not None:
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".csv", delete=False
        ) as tmp:
            tmp.write(uploaded.getvalue())
            tmp_path = tmp.name
        try:
            df = load_class_csv(Path(tmp_path))
            st.write(f"Parsed **{len(df)}** rows:")
            st.dataframe(df, hide_index=True, use_container_width=True)
            if st.button("Register and enroll all", key="csv_btn"):
                records = class_rows_to_records(df)
                with st.spinner("Registering students and computing face encodings..."):
                    try:
                        mapping = service.register_students_for_class(class_id, records)
                        st.success(f"Enrolled {len(mapping)} students in the class.")
                        st.rerun()
                    except RecognitionError as exc:
                        st.error(str(exc))
        finally:
            import os

            os.unlink(tmp_path)


def render_register_student(service: AttendanceService) -> None:
    """Register a new student from an uploaded image (stored as base64)."""
    st.subheader("Register Student")
    with st.expander("Add a student"):
        col1, col2 = st.columns(2)
        name = col1.text_input("Student name", key="new_student_name")
        gender = col2.selectbox(
            "Gender", ["", "Male", "Female", "Other"], key="new_student_gender"
        )
        uploaded = st.file_uploader(
            "Student photo", type=["jpg", "jpeg", "png"], key="new_student_photo"
        )
        if st.button("Register", key="register_btn") and name.strip() and uploaded is not None:
            import base64

            image_base64 = base64.b64encode(uploaded.getvalue()).decode("ascii")
            try:
                student_id = service.register_student(
                    name.strip(), uploaded.name, image_base64, gender or None
                )
                service.embed_student_from_db(student_id)
                st.success(f"Registered {name.strip()} and computed face encoding.")
                st.rerun()
            except RecognitionError as exc:
                st.error(str(exc))


def render_roster(service: AttendanceService, class_id: int | None) -> None:
    st.subheader("Roster (one column per class/session)")
    rows, columns = service.roster(class_id)
    if not rows:
        st.info("No students registered yet.")
        return
    display = pd.DataFrame(rows)
    st.dataframe(display, hide_index=True, use_container_width=True)
    export_name, export_bytes = service.roster_csv(class_id)
    st.download_button(
        "Download Roster CSV",
        data=export_bytes,
        file_name=export_name,
        mime="text/csv",
        use_container_width=True,
    )


def render_reports(service: AttendanceService) -> None:
    st.subheader("Class Attendance Report")
    classes = service.list_classes()
    if not classes:
        st.info("No classes registered yet.")
        return
    names = [c["name"] for c in classes]
    sel = st.selectbox("Select class", names, key="report_class")
    sel_id = int(next(c["id"] for c in classes if c["name"] == sel))

    col1, col2 = st.columns(2)
    start = col1.date_input("From", value=date.today(), key="report_from")
    end = col2.date_input("To", value=date.today(), key="report_to")
    if start > end:
        st.error("'From' date must be on or before 'To' date.")
        return

    if st.button("Generate class report", key="report_class_btn"):
        rows, dates = service.class_attendance_report(sel_id, start, end)
        if not dates:
            st.info("No sessions recorded for this class in the selected range.")
            return
        st.write(f"**Attendance matrix ({len(dates)} session(s)):**")
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        export_name, export_bytes = service.export_class_attendance(sel_id, start, end)
        st.download_button(
            "Download Class Report CSV",
            data=export_bytes,
            file_name=export_name,
            mime="text/csv",
            use_container_width=True,
        )

    st.divider()
    st.subheader("Student Attendance Report")
    students = service.students()
    if not students:
        st.info("No students registered yet.")
        return
    student_names = [s["name"] for s in students]
    student_sel = st.selectbox("Select student", student_names, key="report_student")
    student_id = int(next(s["id"] for s in students if s["name"] == student_sel))

    if st.button("Generate student report", key="report_student_btn"):
        rows = service.student_attendance_report(student_id)
        if not rows:
            st.info("No sessions recorded for this student yet.")
            return
        present = sum(1 for r in rows if r["status"] == "present")
        total = len(rows)
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Sessions", total)
        col_b.metric("Present", present)
        col_c.metric("Attendance", f"{round(present / total * 100)}%" if total else "-")
        st.dataframe(
            pd.DataFrame([dict(r) for r in rows]),
            hide_index=True,
            use_container_width=True,
        )
        export_name, export_bytes = service.export_student_attendance(student_id)
        st.download_button(
            "Download Student Report CSV",
            data=export_bytes,
            file_name=export_name,
            mime="text/csv",
            use_container_width=True,
        )


def render_session_selector(
    service: AttendanceService, class_id: int, day: date
) -> int | None:
    """Let the user pick which session of a class+date to record attendance for.

    Sessions on the same date are listed individually; ``+ New session`` lets the
    user start another session (for multi-session days).
    """
    existing = service.sessions_for_date(class_id, day)
    options: list[str] = []
    ids: list[int | None] = []
    for i, s in enumerate(existing):
        options.append(s["label"] or f"Session {i + 1}")
        ids.append(int(s["id"]))
    options.append("+ New session")
    ids.append(None)

    default_idx = 0
    stored = st.session_state.get("att_selected_session")
    if stored in ids:
        default_idx = ids.index(stored)
    sel = st.selectbox("Session", options, key="att_session_sel", index=default_idx)
    idx = options.index(sel)

    if ids[idx] is None:
        label = st.text_input(
            "New session label (optional, e.g. Morning)", key="att_new_session_label"
        )
        if st.button("Create session", key="att_create_session_btn"):
            sid = service.create_session(class_id, day, label.strip() or None)
            st.session_state["att_selected_session"] = sid
            st.rerun()
        return st.session_state.get("att_selected_session")

    st.session_state["att_selected_session"] = ids[idx]
    return ids[idx]


def render_attendance(service: AttendanceService, class_id: int, threshold: float) -> None:
    day = st.date_input("Attendance date", value=date.today(), key="att_date")
    session_id = render_session_selector(service, class_id, day)
    if session_id is None:
        st.info("Create a session above to begin recording attendance.")
        return

    present, progress = service.summary(session_id)
    total = service.session_total(session_id)

    col1, col2, col3 = st.columns(3)
    col1.metric("Students", total)
    col2.metric("Present", present)
    col3.metric("Progress", f"{progress:.0%}")
    st.progress(progress)

    st.subheader("Mark Attendance")
    st.caption("Upload a group photo; detected faces are matched and marked present.")
    render_upload_image(service, session_id, threshold, class_id)

    st.subheader("Attendance Records")
    rows = service.session_attendance(session_id)
    if not rows:
        st.info("No attendance recorded yet.")
    else:
        st.dataframe(
            pd.DataFrame([dict(r) for r in rows]),
            hide_index=True,
            use_container_width=True,
        )

    export_name, export_bytes = service.export_session_csv(session_id)
    st.download_button(
        "Download CSV",
        data=export_bytes,
        file_name=export_name,
        mime="text/csv",
        use_container_width=True,
    )


def render_upload_image(
    service: AttendanceService, session_id: int, threshold: float, class_id: int
) -> None:
    classes = service.list_classes()
    no_class_label = "— No class (register only) —"
    class_options = [(no_class_label, 0)] + [
        (c["name"], int(c["id"])) for c in classes
    ]
    class_ids = [cid for _, cid in class_options]
    current_index = class_ids.index(class_id) if class_id in class_ids else 0

    scope_label = st.radio(
        "Match faces against",
        ["Only this class", "All classes"],
        horizontal=True,
        key="upload_scope",
        help=(
            "Only this class: match against students enrolled in the selected class. "
            "All classes: match against every registered student."
        ),
    )
    scope_class_id = class_id if scope_label == "Only this class" else None

    uploaded = st.file_uploader(
        "Upload a group photo", type=["jpg", "jpeg", "png"], key="upload_photo"
    )
    unknown_key = "upload_unknown_faces"
    if uploaded is not None:
        st.image(uploaded, caption="Uploaded photo", use_container_width=True)
        if st.button("Run attendance", key="upload_mark_btn"):
            with st.spinner("Recognizing faces..."):
                try:
                    candidates, marks = service.analyze_and_mark_many(
                        session_id,
                        uploaded.getvalue(),
                        threshold,
                        filename=uploaded.name,
                        scope_class_id=scope_class_id,
                    )
                except RecognitionError as exc:
                    st.error(str(exc))
                    candidates, marks = [], []
            if not candidates:
                st.error("No faces detected in the photo. Please try again.")
            else:
                marked = [m for m in marks if m.status == "marked"]
                already = [m for m in marks if m.status == "already_marked"]
                unknown = [c for c in candidates if not c.recognized]
                if marked:
                    st.success("Marked present: " + ", ".join(m.name for m in marked))
                if already:
                    st.warning("Already marked: " + ", ".join(m.name for m in already))
                if unknown:
                    st.session_state[unknown_key] = unknown
                else:
                    st.session_state.pop(unknown_key, None)
                    st.success("All detected faces were recognized.")
            st.rerun()

    unknown = st.session_state.get(unknown_key, [])
    if unknown:
        st.divider()
        st.subheader("Register newly detected persons")
        st.caption(
            "These faces were not matched to registered students. Provide details "
            "and choose a class to enroll them into (and mark present)."
        )
        if st.button("Discard all new faces", key="discard_new_faces"):
            st.session_state.pop(unknown_key, None)
            st.rerun()
        for i, cand in enumerate(unknown):
            with st.expander(
                f"Person {i + 1} — confidence {cand.confidence:.2f}"
            ):
                col1, col2 = st.columns(2)
                col1.image(
                    cand.crop, caption=f"Detected face {i + 1}", use_container_width=True
                )
                name = col2.text_input("Name", key=f"newface_name_{i}")
                gender = col2.selectbox(
                    "Gender", ["", "Male", "Female", "Other"], key=f"newface_gender_{i}"
                )
                target_class = col2.selectbox(
                    "Register into class",
                    [label for label, _ in class_options],
                    index=current_index,
                    key=f"newface_class_{i}",
                )
                target_class_id = dict(class_options)[target_class]
                if col2.button("Register", key=f"newface_btn_{i}"):
                    if not name.strip():
                        st.error("A name is required to register.")
                    else:
                        try:
                            service.register_student_from_crop(
                                target_class_id or None,
                                cand.crop,
                                name.strip(),
                                gender or None,
                                cand.embedding,
                            )
                        except RecognitionError as exc:
                            st.error(str(exc))
                        else:
                            st.session_state[unknown_key].pop(i)
                            if target_class_id:
                                st.success(
                                    f"Registered {name.strip()} into {target_class} "
                                    "and marked present."
                                )
                            else:
                                st.success(f"Registered {name.strip()}.")
                            st.rerun()


def main() -> None:
    st.set_page_config(page_title="Face Attendance", page_icon="📸", layout="centered")
    st.title("Face Recognition Attendance System")
    st.caption(f"Date: {date.today():%A, %d %B %Y}")

    service = get_service()
    seed_students_if_needed(service)

    page = st.sidebar.radio(
        "Page", ["Attendance", "Class Registration", "Reports"]
    )

    if page == "Class Registration":
        render_class_registration(service)
        render_register_student(service)
        return

    if page == "Reports":
        render_reports(service)
        return

    threshold = st.slider(
        "Recognition threshold",
        min_value=0.30,
        max_value=0.60,
        value=DEFAULT_THRESHOLD,
        step=0.01,
        help="Lower values are stricter. A match is accepted only below this face-distance threshold.",
    )

    class_id = render_class_selector(service)
    if class_id is None:
        st.stop()
    render_attendance(service, class_id, threshold)
    render_roster(service, class_id)


if __name__ == "__main__":
    main()
