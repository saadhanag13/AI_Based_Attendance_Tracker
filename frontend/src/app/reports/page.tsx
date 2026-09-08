"use client";

import { useState } from "react";
import useSWR from "swr";
import { format, subDays } from "date-fns";
import {
  getClasses,
  getClassReport,
  getStudents,
  getStudentReport,
  exportClassReport,
  exportStudentReport,
} from "@/lib/api";
import { Class, Student } from "@/lib/types";
import {
  BarChart3,
  Download,
  ChevronRight,
  Users,
  CheckCircle,
  XCircle,
  Loader2,
} from "lucide-react";
import clsx from "clsx";

export default function ReportsPage() {
  const [tab, setTab] = useState<"class" | "student">("class");
  const [selectedClass, setSelectedClass] = useState<number | null>(null);
  const [selectedStudent, setSelectedStudent] = useState<number | null>(null);
  const [from, setFrom] = useState(format(subDays(new Date(), 30), "yyyy-MM-dd"));
  const [to, setTo] = useState(format(new Date(), "yyyy-MM-dd"));

  const { data: classes } = useSWR("report-classes", getClasses);
  const { data: students } = useSWR("report-students", () => getStudents(false));

  const { data: classReport, isLoading: classLoading } = useSWR(
    selectedClass && tab === "class"
      ? `class-report-${selectedClass}-${from}-${to}`
      : null,
    () => getClassReport(selectedClass!, from, to)
  );

  const { data: studentReport, isLoading: studentLoading } = useSWR(
    selectedStudent && tab === "student" ? `student-report-${selectedStudent}` : null,
    () => getStudentReport(selectedStudent!)
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Reports</h1>
        <p className="text-slate-500 text-sm mt-1">
          Attendance analytics and exports
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-slate-100 p-1 rounded-xl w-fit">
        {(["class", "student"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={clsx(
              "px-4 py-2 rounded-lg text-sm font-medium transition-all capitalize",
              tab === t
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-500 hover:text-slate-700"
            )}
          >
            {t} Report
          </button>
        ))}
      </div>

      {/* Class Report */}
      {tab === "class" && (
        <div className="space-y-4">
          <div className="card">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="text-sm font-medium text-slate-700 block mb-1">Class</label>
                <select
                  className="input"
                  value={selectedClass ?? ""}
                  onChange={(e) => setSelectedClass(Number(e.target.value) || null)}
                >
                  <option value="">Select class…</option>
                  {classes?.map((c: Class) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-sm font-medium text-slate-700 block mb-1">From</label>
                <input
                  type="date"
                  className="input"
                  value={from}
                  onChange={(e) => setFrom(e.target.value)}
                />
              </div>
              <div>
                <label className="text-sm font-medium text-slate-700 block mb-1">To</label>
                <input
                  type="date"
                  className="input"
                  value={to}
                  onChange={(e) => setTo(e.target.value)}
                />
              </div>
            </div>
            {selectedClass && (
              <div className="mt-4 flex justify-end">
                <a
                  href={exportClassReport(selectedClass, from, to)}
                  download
                  className="btn-secondary flex items-center gap-2"
                >
                  <Download className="w-4 h-4" />
                  Export CSV
                </a>
              </div>
            )}
          </div>

          {/* Class matrix */}
          {classLoading && (
            <div className="card flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-brand-600" />
            </div>
          )}
          {classReport && classReport.rows.length > 0 && (
            <div className="card overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className="text-left py-3 px-3 font-semibold text-slate-700 sticky left-0 bg-white">
                      Student
                    </th>
                    {classReport.columns.map((col: string) => (
                      <th
                        key={col}
                        className="text-center py-3 px-2 font-medium text-slate-500 text-xs whitespace-nowrap"
                      >
                        {col}
                      </th>
                    ))}
                    <th className="text-center py-3 px-3 font-semibold text-slate-700">
                      Attendance %
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {classReport.rows.map((row: Record<string, string>, i: number) => (
                    <tr
                      key={i}
                      className="border-b border-slate-50 hover:bg-slate-50"
                    >
                      <td className="py-3 px-3 font-medium text-slate-900 sticky left-0 bg-white whitespace-nowrap">
                        {row.Name}
                      </td>
                      {classReport.columns.map((col: string) => (
                        <td key={col} className="py-3 px-2 text-center">
                          {row[col] === "present" ? (
                            <div className="flex justify-center">
                              <CheckCircle className="w-4 h-4 text-emerald-500" />
                            </div>
                          ) : row[col] === "absent" ? (
                            <div className="flex justify-center">
                              <XCircle className="w-4 h-4 text-red-400" />
                            </div>
                          ) : (
                            <span className="text-slate-200">—</span>
                          )}
                        </td>
                      ))}
                      <td className="py-3 px-3 text-center">
                        <span
                          className={clsx(
                            "font-semibold",
                            parseInt(row["Attendance %"]) >= 75
                              ? "text-emerald-600"
                              : parseInt(row["Attendance %"]) >= 50
                              ? "text-amber-500"
                              : "text-red-500"
                          )}
                        >
                          {row["Attendance %"]}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {classReport && classReport.rows.length === 0 && (
            <div className="card text-center py-12">
              <BarChart3 className="w-8 h-8 text-slate-300 mx-auto mb-2" />
              <p className="text-slate-400 text-sm">No data for this range</p>
            </div>
          )}
        </div>
      )}

      {/* Student Report */}
      {tab === "student" && (
        <div className="space-y-4">
          <div className="card">
            <label className="text-sm font-medium text-slate-700 block mb-1">Student</label>
            <select
              className="input"
              value={selectedStudent ?? ""}
              onChange={(e) => setSelectedStudent(Number(e.target.value) || null)}
            >
              <option value="">Select student…</option>
              {students?.map((s: Student) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
            {selectedStudent && (
              <div className="mt-3 flex justify-end">
                <a
                  href={exportStudentReport(selectedStudent)}
                  download
                  className="btn-secondary flex items-center gap-2"
                >
                  <Download className="w-4 h-4" />
                  Export CSV
                </a>
              </div>
            )}
          </div>

          {studentLoading && (
            <div className="card flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-brand-600" />
            </div>
          )}
          {studentReport && (
            <div className="card">
              <div className="grid grid-cols-3 gap-4 mb-6">
                {(() => {
                  const total = studentReport.length;
                  const present = studentReport.filter((r) => r.status === "present").length;
                  const pct = total ? ((present / total) * 100).toFixed(0) : "—";
                  return (
                    <>
                      <div className="text-center p-4 bg-slate-50 rounded-xl">
                        <p className="text-2xl font-bold text-slate-900">{total}</p>
                        <p className="text-xs text-slate-400 mt-1">Total Sessions</p>
                      </div>
                      <div className="text-center p-4 bg-emerald-50 rounded-xl">
                        <p className="text-2xl font-bold text-emerald-700">{present}</p>
                        <p className="text-xs text-slate-400 mt-1">Present</p>
                      </div>
                      <div className="text-center p-4 bg-brand-50 rounded-xl">
                        <p className="text-2xl font-bold text-brand-700">{pct}%</p>
                        <p className="text-xs text-slate-400 mt-1">Attendance</p>
                      </div>
                    </>
                  );
                })()}
              </div>
              <div className="space-y-2">
                {studentReport.map((r: Record<string, string>, i: number) => (
                  <div
                    key={i}
                    className="flex items-center justify-between p-3 rounded-xl hover:bg-slate-50"
                  >
                    <div>
                      <p className="text-sm font-medium text-slate-900">
                        {r.class_name || r.date}
                      </p>
                      <p className="text-xs text-slate-400">
                        {r.date}
                        {r.label ? ` · ${r.label}` : ""}
                      </p>
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
            </div>
          )}
        </div>
      )}
    </div>
  );
}
