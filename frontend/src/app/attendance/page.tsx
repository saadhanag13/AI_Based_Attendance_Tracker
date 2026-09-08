"use client";

import { Suspense } from "react";
import AttendanceContent from "./AttendanceContent";

export default function AttendancePage() {
  return (
    <Suspense fallback={<div className="animate-pulse">Loading…</div>}>
      <AttendanceContent />
    </Suspense>
  );
}
