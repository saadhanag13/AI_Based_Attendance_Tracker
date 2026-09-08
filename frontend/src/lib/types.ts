export interface Class {
  id: number;
  name: string;
  subject: string;
  batch_year: string;
  student_count: number | null;
  enrolled_count: number;
  created_at: string;
}

export interface Student {
  id: number;
  name: string;
  gender: string | null;
  photo: string | null;
  active: number;
  image_b64?: string | null;
  created_at: string;
}

export interface Session {
  id: number;
  class_id: number;
  date: string;
  label: string | null;
  created_at: string;
}

export interface AttendanceRecord {
  name: string;
  status: string;
  distance: number | null;
  confidence: number | null;
  source: string | null;
  marked_at: string;
}

export interface AttendanceSummary {
  present: number;
  total: number;
  progress: number;
}

export interface AnalyzeResult {
  recognized: RecognizedFace[];
  unknown: UnknownFace[];
  total_faces: number;
}

export interface RecognizedFace {
  student_id: number;
  name: string;
  confidence: number;
  distance: number;
  crop_b64: string;
}

export interface UnknownFace {
  crop_b64: string;
  embedding_b64: string;
  confidence: number;
}

export interface ClassReportRow {
  Name: string;
  [date: string]: string;
  "Attendance %": string;
}
