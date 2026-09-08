"use client";

import { useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import { getStudents, registerStudent } from "@/lib/api";
import { Student } from "@/lib/types";
import {
  Users,
  Plus,
  Search,
  Upload,
  Loader2,
  X,
  CheckCircle,
  AlertTriangle,
  User,
} from "lucide-react";
import clsx from "clsx";

export default function StudentsPage() {
  const { data: students, mutate } = useSWR("students-list", () =>
    getStudents(false)
  );
  const [search, setSearch] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", gender: "M" });
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const filtered = students?.filter((s: Student) =>
    s.name.toLowerCase().includes(search.toLowerCase())
  );

  const handleSubmit = async () => {
    if (!form.name.trim() || !file) {
      setError("Please enter a name and select a photo.");
      return;
    }
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await registerStudent({ name: form.name, gender: form.gender, file });
      if (result.warning) {
        setSuccess(`${result.name} registered (face embedding failed: ${result.warning})`);
      } else {
        setSuccess(`${result.name} registered successfully!`);
      }
      setForm({ name: "", gender: "M" });
      setFile(null);
      setPreview(null);
      await mutate();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Students</h1>
          <p className="text-slate-500 text-sm mt-1">
            {students?.length ?? 0} registered students
          </p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="btn-primary flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          Register Student
        </button>
      </div>

      {/* Registration form */}
      {showForm && (
        <div className="card border-2 border-brand-200 bg-brand-50/30">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-slate-900">Register New Student</h2>
            <button
              onClick={() => {
                setShowForm(false);
                setError(null);
                setSuccess(null);
              }}
              className="text-slate-400 hover:text-slate-600"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Photo */}
            <div>
              <label className="text-sm font-medium text-slate-700 block mb-2">Photo</label>
              <label
                className={clsx(
                  "block border-2 border-dashed rounded-2xl cursor-pointer transition-colors overflow-hidden",
                  preview ? "border-brand-300" : "border-slate-200 hover:border-brand-300"
                )}
              >
                {preview ? (
                  <img
                    src={preview}
                    alt="Preview"
                    className="w-full h-48 object-cover"
                  />
                ) : (
                  <div className="h-48 flex flex-col items-center justify-center gap-2 text-slate-400">
                    <Upload className="w-8 h-8" />
                    <p className="text-sm">Click to upload a photo</p>
                    <p className="text-xs">JPG, PNG — one clear face</p>
                  </div>
                )}
                <input
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) {
                      setFile(f);
                      setPreview(URL.createObjectURL(f));
                    }
                  }}
                />
              </label>
            </div>

            {/* Form fields */}
            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium text-slate-700 block mb-1">
                  Full Name
                </label>
                <input
                  className="input"
                  placeholder="e.g. John Smith"
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                />
              </div>

              <div>
                <label className="text-sm font-medium text-slate-700 block mb-1">Gender</label>
                <div className="flex gap-2">
                  {[
                    { value: "M", label: "Male" },
                    { value: "F", label: "Female" },
                    { value: "", label: "Other" },
                  ].map((g) => (
                    <button
                      key={g.value}
                      onClick={() => setForm((f) => ({ ...f, gender: g.value }))}
                      className={clsx(
                        "flex-1 py-2 rounded-xl text-sm border transition-colors",
                        form.gender === g.value
                          ? "bg-brand-600 text-white border-brand-600"
                          : "border-slate-200 text-slate-600 hover:bg-slate-50"
                      )}
                    >
                      {g.label}
                    </button>
                  ))}
                </div>
              </div>

              {success && (
                <div className="flex items-center gap-2 text-emerald-700 bg-emerald-50 p-3 rounded-xl text-sm">
                  <CheckCircle className="w-4 h-4 shrink-0" />
                  {success}
                </div>
              )}
              {error && (
                <div className="flex items-center gap-2 text-red-600 bg-red-50 p-3 rounded-xl text-sm">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  {error}
                </div>
              )}

              <button
                onClick={handleSubmit}
                disabled={submitting}
                className="btn-primary w-full flex items-center justify-center gap-2"
              >
                {submitting ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Plus className="w-4 h-4" />
                )}
                {submitting ? "Registering…" : "Register Student"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
        <input
          className="input pl-9"
          placeholder="Search students…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {/* Students grid */}
      {filtered?.length === 0 ? (
        <div className="card text-center py-12">
          <Users className="w-10 h-10 text-slate-300 mx-auto mb-3" />
          <h3 className="font-medium text-slate-600">No students found</h3>
          <p className="text-sm text-slate-400 mt-1">
            {search ? "Try a different search." : "Register your first student above."}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
          {filtered?.map((s: Student) => (
            <Link
              key={s.id}
              href={`/students/${s.id}`}
              className="card p-4 flex flex-col items-center gap-3 hover:shadow-md transition-all cursor-pointer"
            >
              <div className="w-16 h-16 rounded-2xl bg-brand-100 overflow-hidden flex items-center justify-center">
                <img
                  src={`/api/students/${s.id}/photo`}
                  alt={s.name}
                  className="w-full h-full object-cover"
                  onError={(e) => {
                    const el = e.target as HTMLImageElement;
                    el.style.display = "none";
                    el.parentElement!.innerHTML = `<div class="w-full h-full flex items-center justify-center"><span class="text-xl font-bold text-brand-600">${s.name[0]}</span></div>`;
                  }}
                />
              </div>
              <div className="text-center w-full">
                <p className="text-sm font-semibold text-slate-900 truncate">{s.name}</p>
                <p className="text-xs text-slate-400 mt-0.5">
                  {s.gender === "M" ? "Male" : s.gender === "F" ? "Female" : "—"}
                </p>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
