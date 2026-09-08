"use client";

import { use } from "react";
import useSWR from "swr";
import Link from "next/link";
import { getStudent, getStudentReport, exportStudentReport } from "@/lib/api";
import {
  ArrowLeft,
  Download,
  CheckCircle,
  XCircle,
  Calendar,
  BookOpen,
} from "lucide-react";
import clsx from "clsx";

export default function StudentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const studentId = parseInt(id);

  const { data: student } = useSWR(`student-${studentId}`, () =>
    getStudent(studentId)
  );
  const { data: report } = useSWR(`student-report-${studentId}`, () =>
    getStudentReport(studentId)
  );

  const totalSessions = report?.length ?? 0;
  const presentSessions = report?.filter((r) => r.status === "present").length ?? 0;
  const pct = totalSessions > 0 ? ((presentSessions / totalSessions) * 100).toFixed(0) : "—";

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link href="/students" className="btn-secondary flex items-center gap-1 py-1.5">
          <ArrowLeft className="w-4 h-4" />
          Back
        </Link>
      </div>

      {/* Profile card */}
      <div className="card">
        <div className="flex items-center gap-5">
          <div className="w-20 h-20 rounded-2xl bg-brand-100 overflow-hidden flex items-center justify-center shrink-0">
            <img
              src={`/api/students/${studentId}/photo`}
              alt={student?.name}
              className="w-full h-full object-cover"
              onError={(e) => {
                const el = e.target as HTMLImageElement;
                el.style.display = "none";
                if (student?.name) {
                  el.parentElement!.innerHTML = `<span class="text-3xl font-bold text-brand-600">${student.name[0]}</span>`;
                }
              }}
            />
          </div>
          <div className="flex-1">
            <h1 className="text-2xl font-bold text-slate-900">
              {student?.name ?? "Loading…"}
            </h1>
            <p className="text-slate-500 text-sm mt-1">
              {student?.gender === "M"
                ? "Male"
                : student?.gender === "F"
                ? "Female"
                : "—"}{" "}
              · ID #{student?.id}
            </p>
          </div>
          <a
            href={exportStudentReport(studentId)}
            download
            className="btn-secondary flex items-center gap-2"
          >
            <Download className="w-4 h-4" />
            Export CSV
          </a>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-4 mt-6 pt-6 border-t border-slate-100">
          <div className="text-center">
            <p className="text-2xl font-bold text-slate-900">{totalSessions}</p>
            <p className="text-xs text-slate-400 mt-1">Total Sessions</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-emerald-600">{presentSessions}</p>
            <p className="text-xs text-slate-400 mt-1">Present</p>
          </div>
          <div className="text-center">
            <p
              className={clsx(
                "text-2xl font-bold",
                parseInt(pct) >= 75
                  ? "text-emerald-600"
                  : parseInt(pct) >= 50
                  ? "text-amber-600"
                  : "text-red-500"
              )}
            >
              {pct}%
            </p>
            <p className="text-xs text-slate-400 mt-1">Attendance</p>
          </div>
        </div>
        {totalSessions > 0 && (
          <div className="mt-3 bg-slate-100 rounded-full h-2 overflow-hidden">
            <div
              className={clsx(
                "h-full rounded-full transition-all",
                parseInt(pct) >= 75
                  ? "bg-emerald-500"
                  : parseInt(pct) >= 50
                  ? "bg-amber-400"
                  : "bg-red-400"
              )}
              style={{ width: `${pct}%` }}
            />
          </div>
        )}
      </div>

      {/* Attendance History */}
      <div className="card">
        <h2 className="font-semibold text-slate-900 mb-4">Attendance History</h2>
        {!report || report.length === 0 ? (
          <div className="text-center py-8">
            <Calendar className="w-8 h-8 text-slate-300 mx-auto mb-2" />
            <p className="text-sm text-slate-400">No attendance records yet</p>
          </div>
        ) : (
          <div className="space-y-2">
            {report.map((r, i) => (
              <div
                key={i}
                className="flex items-center justify-between p-3 rounded-xl hover:bg-slate-50"
              >
                <div className="flex items-center gap-3">
                  <div
                    className={clsx(
                      "w-8 h-8 rounded-lg flex items-center justify-center",
                      r.status === "present"
                        ? "bg-emerald-100"
                        : "bg-red-100"
                    )}
                  >
                    {r.status === "present" ? (
                      <CheckCircle className="w-4 h-4 text-emerald-600" />
                    ) : (
                      <XCircle className="w-4 h-4 text-red-500" />
                    )}
                  </div>
                  <div>
                    <p className="text-sm font-medium text-slate-900">
                      {r.class_name ?? r.date}
                    </p>
                    <p className="text-xs text-slate-400">
                      {r.date}
                      {r.label ? ` · ${r.label}` : ""}
                    </p>
                  </div>
                </div>
                <span
                  className={
                    r.status === "present" ? "badge-present" : "badge-absent"
                  }
                >
                  {r.status}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
