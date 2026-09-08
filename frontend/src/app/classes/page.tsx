"use client";

import { useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import {
  getClasses,
  createClass,
  getClassStudents,
  getStudents,
  enrollStudents,
  removeFromClass,
} from "@/lib/api";
import { Class, Student } from "@/lib/types";
import {
  BookOpen,
  Plus,
  Users,
  Camera,
  ChevronDown,
  ChevronRight,
  X,
  Loader2,
  CheckCircle,
  Search,
} from "lucide-react";
import clsx from "clsx";

export default function ClassesPage() {
  const { data: classes, mutate: mutateClasses } = useSWR("classes-page", getClasses);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    name: "",
    subject: "",
    batch_year: new Date().getFullYear().toString(),
    student_count: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [expandedClass, setExpandedClass] = useState<number | null>(null);

  const handleCreate = async () => {
    if (!form.name.trim()) return;
    setSubmitting(true);
    try {
      await createClass({
        name: form.name,
        subject: form.subject,
        batch_year: form.batch_year,
        student_count: form.student_count ? parseInt(form.student_count) : undefined,
      });
      setForm({ name: "", subject: "", batch_year: new Date().getFullYear().toString(), student_count: "" });
      setShowForm(false);
      await mutateClasses();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Classes</h1>
          <p className="text-slate-500 text-sm mt-1">
            {classes?.length ?? 0} classes · manage rosters
          </p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="btn-primary flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          New Class
        </button>
      </div>

      {/* Create form */}
      {showForm && (
        <div className="card border-2 border-brand-200 bg-brand-50/30">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-slate-900">Create New Class</h2>
            <button onClick={() => setShowForm(false)} className="text-slate-400 hover:text-slate-600">
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-slate-700 block mb-1">Class Name *</label>
              <input
                className="input"
                placeholder="e.g. Grade 10A"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              />
            </div>
            <div>
              <label className="text-sm font-medium text-slate-700 block mb-1">Subject</label>
              <input
                className="input"
                placeholder="e.g. Mathematics"
                value={form.subject}
                onChange={(e) => setForm((f) => ({ ...f, subject: e.target.value }))}
              />
            </div>
            <div>
              <label className="text-sm font-medium text-slate-700 block mb-1">Batch Year</label>
              <input
                className="input"
                placeholder="e.g. 2025"
                value={form.batch_year}
                onChange={(e) => setForm((f) => ({ ...f, batch_year: e.target.value }))}
              />
            </div>
            <div>
              <label className="text-sm font-medium text-slate-700 block mb-1">
                Expected Students (optional)
              </label>
              <input
                type="number"
                className="input"
                placeholder="e.g. 30"
                value={form.student_count}
                onChange={(e) => setForm((f) => ({ ...f, student_count: e.target.value }))}
              />
            </div>
          </div>
          <div className="flex justify-end mt-4">
            <button
              onClick={handleCreate}
              disabled={submitting || !form.name.trim()}
              className="btn-primary flex items-center gap-2"
            >
              {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
              Create Class
            </button>
          </div>
        </div>
      )}

      {/* Classes list */}
      <div className="space-y-3">
        {classes?.length === 0 && (
          <div className="card text-center py-12">
            <BookOpen className="w-10 h-10 text-slate-300 mx-auto mb-3" />
            <h3 className="font-medium text-slate-600">No classes yet</h3>
            <p className="text-sm text-slate-400 mt-1">Create your first class to get started.</p>
          </div>
        )}
        {classes?.map((cls: Class) => (
          <ClassRow
            key={cls.id}
            cls={cls}
            expanded={expandedClass === cls.id}
            onToggle={() => setExpandedClass(expandedClass === cls.id ? null : cls.id)}
            onRosterChange={mutateClasses}
          />
        ))}
      </div>
    </div>
  );
}

function ClassRow({
  cls,
  expanded,
  onToggle,
  onRosterChange,
}: {
  cls: Class;
  expanded: boolean;
  onToggle: () => void;
  onRosterChange: () => void;
}) {
  const { data: classStudents, mutate: mutateClassStudents } = useSWR(
    expanded ? `class-students-${cls.id}` : null,
    () => getClassStudents(cls.id)
  );
  const { data: allStudents } = useSWR(
    expanded ? "all-students-for-class" : null,
    () => getStudents(false)
  );
  const [search, setSearch] = useState("");
  const [adding, setAdding] = useState(false);

  const enrolledIds = new Set(classStudents?.map((s: Student) => s.id));
  const unenrolled = allStudents?.filter(
    (s: Student) =>
      !enrolledIds.has(s.id) &&
      s.name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="card">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between"
      >
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 bg-brand-100 rounded-xl flex items-center justify-center">
            <BookOpen className="w-5 h-5 text-brand-600" />
          </div>
          <div className="text-left">
            <p className="font-semibold text-slate-900">{cls.name}</p>
            <p className="text-sm text-slate-400">
              {cls.subject}
              {cls.batch_year ? ` · Batch ${cls.batch_year}` : ""}
              {" · "}
              <span className="text-brand-600 font-medium">{cls.enrolled_count} enrolled</span>
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href={`/attendance?class_id=${cls.id}`}
            onClick={(e) => e.stopPropagation()}
            className="btn-primary py-1.5 px-3 text-sm flex items-center gap-1"
          >
            <Camera className="w-3 h-3" />
            Attend
          </Link>
          {expanded ? (
            <ChevronDown className="w-4 h-4 text-slate-400" />
          ) : (
            <ChevronRight className="w-4 h-4 text-slate-400" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="mt-5 pt-5 border-t border-slate-100 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-medium text-slate-800">
              Enrolled Students ({classStudents?.length ?? 0})
            </h3>
            <button
              onClick={() => setAdding(!adding)}
              className="btn-secondary text-sm flex items-center gap-1"
            >
              <Plus className="w-3 h-3" />
              Add Students
            </button>
          </div>

          {/* Enrolled list */}
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
            {classStudents?.map((s: Student) => (
              <div
                key={s.id}
                className="flex items-center justify-between p-2 rounded-xl bg-slate-50 text-sm"
              >
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-full bg-brand-100 overflow-hidden flex items-center justify-center">
                    <img
                      src={`/api/students/${s.id}/photo`}
                      alt={s.name}
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = "none";
                      }}
                    />
                  </div>
                  <span className="truncate font-medium text-slate-700 text-xs">
                    {s.name}
                  </span>
                </div>
                <button
                  onClick={async () => {
                    await removeFromClass(cls.id, s.id);
                    await mutateClassStudents();
                    onRosterChange();
                  }}
                  className="text-slate-300 hover:text-red-400 transition-colors"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            ))}
            {classStudents?.length === 0 && (
              <p className="col-span-full text-sm text-slate-400 text-center py-4">
                No students enrolled yet
              </p>
            )}
          </div>

          {/* Add students panel */}
          {adding && (
            <div className="border border-slate-200 rounded-xl p-4 space-y-3">
              <h4 className="text-sm font-medium text-slate-700">Add from registered students</h4>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-400" />
                <input
                  className="input pl-8 py-1.5 text-sm"
                  placeholder="Search students…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>
              <div className="max-h-48 overflow-y-auto space-y-1">
                {unenrolled?.map((s: Student) => (
                  <button
                    key={s.id}
                    onClick={async () => {
                      await enrollStudents(cls.id, [s.id]);
                      await mutateClassStudents();
                      onRosterChange();
                    }}
                    className="w-full flex items-center gap-2 p-2 rounded-lg hover:bg-brand-50 transition-colors text-left"
                  >
                    <div className="w-6 h-6 rounded-full bg-brand-100 overflow-hidden flex items-center justify-center shrink-0">
                      <img
                        src={`/api/students/${s.id}/photo`}
                        alt={s.name}
                        className="w-full h-full object-cover"
                        onError={(e) => (e.target as HTMLImageElement).style.display = "none"}
                      />
                    </div>
                    <span className="text-sm text-slate-700">{s.name}</span>
                    <Plus className="w-3 h-3 text-brand-500 ml-auto" />
                  </button>
                ))}
                {unenrolled?.length === 0 && (
                  <p className="text-sm text-slate-400 text-center py-4">
                    All students enrolled or none match
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
