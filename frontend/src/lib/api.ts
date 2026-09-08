import type {
  Class,
  Student,
  Session,
  AttendanceRecord,
  AttendanceSummary,
  AnalyzeResult,
} from "./types";

const BASE = "/api";

async function req<T>(url: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(BASE + url, opts);
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ── Classes ──────────────────────────────────────────────────────────────────

export const getClasses = () => req<Class[]>("/classes");

export const getClass = (id: number) => req<Class>(`/classes/${id}`);

export const createClass = (data: {
  name: string;
  subject: string;
  batch_year: string;
  student_count?: number;
}) => {
  const fd = new FormData();
  fd.append("name", data.name);
  fd.append("subject", data.subject);
  fd.append("batch_year", data.batch_year);
  if (data.student_count) fd.append("student_count", String(data.student_count));
  return req<Class>("/classes", { method: "POST", body: fd });
};

export const getClassStudents = (classId: number) =>
  req<Student[]>(`/classes/${classId}/students`);

export const enrollStudents = (classId: number, studentIds: number[]) =>
  req(`/classes/${classId}/students`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(studentIds),
  });

export const removeFromClass = (classId: number, studentId: number) =>
  req(`/classes/${classId}/students/${studentId}`, { method: "DELETE" });

// ── Students ─────────────────────────────────────────────────────────────────

export const getStudents = (includeImage = false) =>
  req<Student[]>(`/students?include_image=${includeImage}`);

export const getStudent = (id: number) =>
  req<Student>(`/students/${id}?include_image=true`);

export const registerStudent = (data: {
  name: string;
  gender: string;
  file: File;
}) => {
  const fd = new FormData();
  fd.append("name", data.name);
  fd.append("gender", data.gender);
  fd.append("file", data.file);
  return req<{ id: number; name: string; warning?: string }>("/students", {
    method: "POST",
    body: fd,
  });
};

export const registerFromCrop = (data: {
  name: string;
  gender: string;
  class_id?: number;
  session_id?: number;
  crop_b64: string;
  embedding_b64: string;
}) => {
  const fd = new FormData();
  fd.append("name", data.name);
  fd.append("gender", data.gender);
  if (data.class_id) fd.append("class_id", String(data.class_id));
  if (data.session_id) fd.append("session_id", String(data.session_id));
  fd.append("crop_b64", data.crop_b64);
  fd.append("embedding_b64", data.embedding_b64);
  return req<{ id: number; name: string }>("/students/register-crop", {
    method: "POST",
    body: fd,
  });
};

export const getStudentPhoto = (id: number) => `/api/students/${id}/photo`;

// ── Sessions ─────────────────────────────────────────────────────────────────

export const getSessions = (classId: number, day?: string) => {
  const qs = day ? `&day=${day}` : "";
  return req<Session[]>(`/sessions?class_id=${classId}${qs}`);
};

export const createSession = (data: {
  class_id: number;
  day: string;
  label?: string;
}) => {
  const fd = new FormData();
  fd.append("class_id", String(data.class_id));
  fd.append("day", data.day);
  if (data.label) fd.append("label", data.label);
  return req<Session>("/sessions", { method: "POST", body: fd });
};

// ── Attendance ────────────────────────────────────────────────────────────────

export const analyzeAttendance = (data: {
  session_id: number;
  threshold: number;
  scope: "class" | "all";
  file: File | Blob;
}) => {
  const fd = new FormData();
  fd.append("session_id", String(data.session_id));
  fd.append("threshold", String(data.threshold));
  fd.append("scope", data.scope);
  fd.append("file", data.file, "capture.jpg");
  return req<AnalyzeResult>("/attendance/analyze", { method: "POST", body: fd });
};

export const applyAttendance = (sessionId: number, studentIds: number[]) =>
  req("/attendance/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, student_ids: studentIds }),
  });

export const getAttendance = (sessionId: number) =>
  req<AttendanceRecord[]>(`/attendance?session_id=${sessionId}`);

export const getAttendanceSummary = (sessionId: number) =>
  req<AttendanceSummary>(`/attendance/summary?session_id=${sessionId}`);

export const toggleAttendance = (sessionId: number, studentId: number) =>
  req<{ status: string }>(`/attendance/toggle?session_id=${sessionId}&student_id=${studentId}`, {
    method: "POST",
  });

export const exportAttendance = (sessionId: number) =>
  `/api/attendance/export?session_id=${sessionId}`;

// ── Reports ───────────────────────────────────────────────────────────────────

export const getClassReport = (classId: number, from: string, to: string) =>
  req<{ rows: Record<string, string>[]; columns: string[] }>(
    `/reports/class?class_id=${classId}&from=${from}&to=${to}`
  );

export const exportClassReport = (classId: number, from: string, to: string) =>
  `/api/reports/class?class_id=${classId}&from=${from}&to=${to}&export=true`;

export const getStudentReport = (studentId: number) =>
  req<Record<string, string>[]>(`/reports/student?student_id=${studentId}`);

export const exportStudentReport = (studentId: number) =>
  `/api/reports/student?student_id=${studentId}&export=true`;
