"use client";

import { useState, useRef, useCallback } from "react";
import useSWR from "swr";
import { useSearchParams } from "next/navigation";
import { format } from "date-fns";
import {
  Camera,
  Upload,
  CheckCircle,
  AlertTriangle,
  RefreshCw,
  Download,
  Plus,
  Loader2,
  UserPlus,
} from "lucide-react";
import {
  getClasses,
  getSessions,
  createSession,
  analyzeAttendance,
  applyAttendance,
  getAttendance,
  getAttendanceSummary,
  toggleAttendance,
  exportAttendance,
  registerFromCrop,
} from "@/lib/api";
import type {
  Class,
  Session,
  AnalyzeResult,
  RecognizedFace,
  UnknownFace,
} from "@/lib/types";
import clsx from "clsx";

type Step = "setup" | "capture" | "review" | "done";

export default function AttendanceContent() {
  const searchParams = useSearchParams();
  const preselectedClass = searchParams.get("class_id");

  const [step, setStep] = useState<Step>("setup");
  const [selectedClass, setSelectedClass] = useState<number | null>(
    preselectedClass ? parseInt(preselectedClass) : null
  );
  const [selectedSession, setSelectedSession] = useState<Session | null>(null);
  const [today, setToday] = useState(format(new Date(), "yyyy-MM-dd"));
  const [sessionLabel, setSessionLabel] = useState("");
  const [threshold, setThreshold] = useState(0.48);
  const [scope, setScope] = useState<"class" | "all">("class");

  const [preview, setPreview] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysis, setAnalysis] = useState<AnalyzeResult | null>(null);

  const [confirmedIds, setConfirmedIds] = useState<Set<number>>(new Set());
  const [applying, setApplying] = useState(false);

  const [cameraActive, setCameraActive] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [registeringIdx, setRegisteringIdx] = useState<number | null>(null);
  const [registerForm, setRegisterForm] = useState({ name: "", gender: "M" });

  const { data: classes } = useSWR("classes", getClasses);
  const { data: sessions, mutate: mutateSessions } = useSWR(
    selectedClass && today ? `sessions-${selectedClass}-${today}` : null,
    () => getSessions(selectedClass!, today)
  );
  const { data: attendance, mutate: mutateAttendance } = useSWR(
    selectedSession ? `attendance-${selectedSession.id}` : null,
    () => getAttendance(selectedSession!.id)
  );
  const { data: summary, mutate: mutateSummary } = useSWR(
    selectedSession ? `summary-${selectedSession.id}` : null,
    () => getAttendanceSummary(selectedSession!.id)
  );

  const selectedClassObj = classes?.find((c: Class) => c.id === selectedClass);

  const startCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      streamRef.current = stream;
      if (videoRef.current) videoRef.current.srcObject = stream;
      setCameraActive(true);
    } catch {
      alert("Cannot access camera. Please check permissions.");
    }
  };

  const stopCamera = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setCameraActive(false);
  };

  const captureFrame = useCallback((): Promise<Blob | null> => {
    const video = videoRef.current;
    if (!video) return Promise.resolve(null);
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d")!;
    ctx.drawImage(video, 0, 0);
    return new Promise<Blob | null>((res) =>
      canvas.toBlob((b) => res(b), "image/jpeg", 0.92)
    );
  }, []);

  const handleFile = async (file: File | Blob) => {
    const url = URL.createObjectURL(file);
    setPreview(url);
    if (!selectedSession) return;
    setAnalyzing(true);
    try {
      const result = await analyzeAttendance({
        session_id: selectedSession.id,
        threshold,
        scope,
        file,
      });
      setAnalysis(result);
      setConfirmedIds(new Set(result.recognized.map((r) => r.student_id)));
      setStep("review");
    } catch (e: unknown) {
      alert(
        "Analysis failed: " + (e instanceof Error ? e.message : String(e))
      );
    } finally {
      setAnalyzing(false);
    }
  };

  const handleCapture = async () => {
    const blob = await captureFrame();
    if (blob) {
      stopCamera();
      await handleFile(blob);
    }
  };

  const handleApply = async () => {
    if (!selectedSession) return;
    setApplying(true);
    try {
      await applyAttendance(selectedSession.id, Array.from(confirmedIds.values()));
      await mutateAttendance();
      await mutateSummary();
      setStep("done");
    } catch (e: unknown) {
      alert("Failed: " + (e instanceof Error ? e.message : String(e)));
    } finally {
      setApplying(false);
    }
  };

  const handleNewSession = async () => {
    if (!selectedClass) return;
    const sess = await createSession({
      class_id: selectedClass,
      day: today,
      label: sessionLabel || undefined,
    });
    await mutateSessions();
    setSelectedSession(sess);
    setSessionLabel("");
  };

  const handleRegisterCrop = async (face: UnknownFace, idx: number) => {
    if (!registerForm.name.trim()) return;
    try {
      const result = await registerFromCrop({
        name: registerForm.name,
        gender: registerForm.gender,
        class_id: selectedClass ?? undefined,
        session_id: selectedSession?.id,
        crop_b64: face.crop_b64,
        embedding_b64: face.embedding_b64,
      });
      setConfirmedIds((prev) => { const n = new Set(Array.from(prev)); n.add(result.id); return n; });
      setRegisteringIdx(null);
      setRegisterForm({ name: "", gender: "M" });
      setAnalysis((prev) =>
        prev
          ? {
              ...prev,
              unknown: prev.unknown.filter((_, i) => i !== idx),
              recognized: [
                ...prev.recognized,
                {
                  student_id: result.id,
                  name: result.name,
                  confidence: face.confidence,
                  distance: 0,
                  crop_b64: face.crop_b64,
                },
              ],
            }
          : prev
      );
    } catch (e: unknown) {
      alert(
        "Registration failed: " + (e instanceof Error ? e.message : String(e))
      );
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Attendance</h1>
        <p className="text-slate-500 text-sm mt-1">
          Take a photo to mark attendance automatically
        </p>
      </div>

      {/* Progress Steps */}
      <div className="flex items-center gap-2 flex-wrap">
        {(["setup", "capture", "review", "done"] as Step[]).map((s, i) => {
          const steps: Step[] = ["setup", "capture", "review", "done"];
          const currentIdx = steps.indexOf(step);
          const thisIdx = i;
          return (
            <div key={s} className="flex items-center gap-2">
              <div
                className={clsx(
                  "w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold",
                  step === s
                    ? "bg-brand-600 text-white"
                    : thisIdx < currentIdx
                    ? "bg-accent-600 text-white"
                    : "bg-blue-100 text-blue-400"
                )}
              >
                {thisIdx < currentIdx ? "✓" : i + 1}
              </div>
              <span
                className={clsx(
                  "text-xs font-medium capitalize",
                  step === s ? "text-brand-700" : "text-blue-400"
                )}
              >
                {s}
              </span>
              {i < 3 && <div className="w-6 h-px bg-blue-200" />}
            </div>
          );
        })}
      </div>

      {/* ── Step 1: Setup ─────────────────────────────────────────────── */}
      {step === "setup" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="card space-y-4">
            <h2 className="font-semibold text-slate-900 flex items-center gap-2">
              <span className="w-1.5 h-1.5 bg-brand-600 rounded-full"></span>
              Session Setup
            </h2>

            <div>
              <label className="text-sm font-medium text-slate-700 block mb-1">
                Class
              </label>
              <select
                className="input"
                value={selectedClass ?? ""}
                onChange={(e) =>
                  setSelectedClass(Number(e.target.value) || null)
                }
              >
                <option value="">Select a class…</option>
                {classes?.map((c: Class) => (
                  <option key={c.id} value={c.id}>
                    {c.name} — {c.subject}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700 block mb-1">
                Date
              </label>
              <input
                type="date"
                className="input"
                value={today}
                onChange={(e) => setToday(e.target.value)}
              />
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700 block mb-1">
                Recognition Threshold
              </label>
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min={0.3}
                  max={0.6}
                  step={0.01}
                  value={threshold}
                  onChange={(e) => setThreshold(parseFloat(e.target.value))}
                  className="flex-1 accent-brand-600"
                />
                <span className="text-sm font-mono text-slate-600 w-10">
                  {threshold.toFixed(2)}
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-1">
                Lower = stricter matching. Default 0.48 works well.
              </p>
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700 block mb-1">
                Scope
              </label>
              <div className="flex gap-3">
                {(["class", "all"] as const).map((s) => (
                  <button
                    key={s}
                    onClick={() => setScope(s)}
                    className={clsx(
                      "flex-1 py-2 rounded-xl text-sm font-medium border transition-colors",
                      scope === s
                        ? "bg-brand-600 text-white border-brand-600"
                        : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"
                    )}
                  >
                    {s === "class" ? "This class only" : "All students"}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="card space-y-4">
            <h2 className="font-semibold text-slate-900 flex items-center gap-2">
              <span className="w-1.5 h-1.5 bg-accent-600 rounded-full"></span>
              Select Session
            </h2>

            {!selectedClass ? (
              <div className="text-center py-8">
                <AlertTriangle className="w-8 h-8 text-amber-400 mx-auto mb-2" />
                <p className="text-sm text-slate-400">Select a class first</p>
              </div>
            ) : (
              <>
                <div className="space-y-2">
                  {sessions?.length === 0 && (
                    <p className="text-sm text-slate-400 text-center py-4">
                      No sessions for this date — create one below
                    </p>
                  )}
                  {sessions?.map((s: Session) => (
                    <button
                      key={s.id}
                      onClick={() => setSelectedSession(s)}
                      className={clsx(
                        "w-full flex items-center justify-between p-3 rounded-xl border text-sm transition-all",
                        selectedSession?.id === s.id
                          ? "border-brand-500 bg-brand-50 text-brand-700"
                          : "border-blue-200 hover:border-blue-300 text-slate-700"
                      )}
                    >
                      <span>
                        {s.label || "Session"}{" "}
                        <span className="text-slate-400">· {s.date}</span>
                      </span>
                      {selectedSession?.id === s.id && (
                        <CheckCircle className="w-4 h-4 text-brand-600" />
                      )}
                    </button>
                  ))}
                </div>

                <div className="border-t border-blue-100 pt-3">
                  <p className="text-xs font-medium text-slate-500 mb-2">
                    Create new session
                  </p>
                  <div className="flex gap-2">
                    <input
                      className="input flex-1"
                      placeholder="Label (e.g. Morning)"
                      value={sessionLabel}
                      onChange={(e) => setSessionLabel(e.target.value)}
                    />
                    <button
                      onClick={handleNewSession}
                      className="btn-primary flex items-center gap-1 whitespace-nowrap"
                    >
                      <Plus className="w-4 h-4" />
                      New
                    </button>
                  </div>
                </div>

                <button
                  disabled={!selectedSession}
                  onClick={() => setStep("capture")}
                  className="btn-primary w-full disabled:opacity-40"
                >
                  Continue to Capture →
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {/* ── Step 2: Capture ───────────────────────────────────────────── */}
      {step === "capture" && (
        <div className="card max-w-2xl mx-auto space-y-5">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-slate-900">
              {selectedClassObj?.name} —{" "}
              {selectedSession?.label || "Session"} · {selectedSession?.date}
            </h2>
            <button
              onClick={() => setStep("setup")}
              className="text-sm text-slate-400 hover:text-slate-600"
            >
              ← Back
            </button>
          </div>

          <div className="relative bg-gradient-to-br from-slate-900 to-blue-900 rounded-2xl overflow-hidden aspect-video">
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              className={clsx(
                "w-full h-full object-cover",
                !cameraActive && "hidden"
              )}
            />
            {!cameraActive && !analyzing && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-slate-500">
                <Camera className="w-14 h-14 opacity-30" />
                <p className="text-sm">Open camera or upload a photo</p>
              </div>
            )}
            {analyzing && (
              <div className="absolute inset-0 bg-black/70 flex flex-col items-center justify-center gap-3">
                <Loader2 className="w-10 h-10 text-white animate-spin" />
                <p className="text-white text-sm font-medium">
                  Detecting faces…
                </p>
              </div>
            )}
          </div>

          <div className="flex gap-3">
            {!cameraActive ? (
              <button
                onClick={startCamera}
                disabled={analyzing}
                className="btn-primary flex-1 flex items-center justify-center gap-2"
              >
                <Camera className="w-4 h-4" />
                Open Camera
              </button>
            ) : (
              <>
                <button
                  onClick={handleCapture}
                  disabled={analyzing}
                  className="btn-primary flex-1 flex items-center justify-center gap-2"
                >
                  <Camera className="w-4 h-4" />
                  Capture & Analyze
                </button>
                <button onClick={stopCamera} className="btn-secondary">
                  Stop
                </button>
              </>
            )}
            <label
              className={clsx(
                "btn-secondary flex items-center gap-2 cursor-pointer",
                analyzing && "opacity-50 pointer-events-none"
              )}
            >
              <Upload className="w-4 h-4" />
              Upload
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleFile(f);
                }}
              />
            </label>
          </div>
        </div>
      )}

      {/* ── Step 3: Review ────────────────────────────────────────────── */}
      {step === "review" && analysis && (
        <div className="space-y-5">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div>
              <h2 className="font-semibold text-slate-900">Review Attendance</h2>
              <p className="text-sm text-slate-400">
                {analysis.total_faces} face
                {analysis.total_faces !== 1 ? "s" : ""} detected ·{" "}
                {analysis.recognized.length} recognized ·{" "}
                {analysis.unknown.length} unknown
              </p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => {
                  setAnalysis(null);
                  setPreview(null);
                  setStep("capture");
                }}
                className="btn-secondary flex items-center gap-2"
              >
                <RefreshCw className="w-4 h-4" />
                Re-capture
              </button>
              <button
                onClick={handleApply}
                disabled={applying}
                className="btn-primary flex items-center gap-2"
              >
                {applying ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <CheckCircle className="w-4 h-4" />
                )}
                Confirm {confirmedIds.size} Present
              </button>
            </div>
          </div>

          {preview && (
            <div className="card p-3">
              <img
                src={preview}
                alt="Captured"
                className="w-full max-h-64 object-contain rounded-xl bg-slate-50"
              />
            </div>
          )}

          {analysis.recognized.length > 0 && (
            <div className="card">
              <h3 className="font-medium text-slate-900 mb-4 flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-accent-500" />
                Recognized ({analysis.recognized.length}) — tap to toggle
              </h3>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
                {analysis.recognized.map((face: RecognizedFace) => {
                  const confirmed = confirmedIds.has(face.student_id);
                  return (
                    <button
                      key={face.student_id}
                      onClick={() => {
                        setConfirmedIds((prev) => {
                          const next = new Set(Array.from(prev));
                          confirmed
                            ? next.delete(face.student_id)
                            : next.add(face.student_id);
                          return next;
                        });
                      }}
                      className={clsx(
                        "relative rounded-2xl overflow-hidden border-2 transition-all text-left",
                        confirmed
                          ? "border-accent-500 shadow-sm"
                          : "border-blue-200 opacity-40 grayscale"
                      )}
                    >
                      <img
                        src={`data:image/jpeg;base64,${face.crop_b64}`}
                        alt={face.name}
                        className="w-full aspect-square object-cover"
                      />
                      <div className="p-2 bg-white">
                        <p className="text-xs font-semibold text-slate-900 truncate">
                          {face.name}
                        </p>
                        <p className="text-xs text-slate-400">
                          {(face.confidence * 100).toFixed(0)}% conf
                        </p>
                      </div>
                      {confirmed && (
                        <div className="absolute top-1.5 right-1.5 bg-accent-500 rounded-full p-0.5">
                          <CheckCircle className="w-3 h-3 text-white" />
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {analysis.unknown.length > 0 && (
            <div className="card">
              <h3 className="font-medium text-slate-900 mb-4 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-brand-600" />
                Unknown Faces ({analysis.unknown.length}) — register or skip
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
                {analysis.unknown.map((face: UnknownFace, idx) => (
                  <div
                    key={idx}
                    className="border border-dashed border-blue-300 bg-blue-50/30 rounded-2xl overflow-hidden"
                  >
                    <img
                      src={`data:image/jpeg;base64,${face.crop_b64}`}
                      alt="Unknown"
                      className="w-full aspect-square object-cover"
                    />
                    {registeringIdx === idx ? (
                      <div className="p-3 space-y-2">
                        <input
                          className="input text-sm"
                          placeholder="Full name"
                          value={registerForm.name}
                          onChange={(e) =>
                            setRegisterForm((f) => ({
                              ...f,
                              name: e.target.value,
                            }))
                          }
                        />
                        <select
                          className="input text-sm"
                          value={registerForm.gender}
                          onChange={(e) =>
                            setRegisterForm((f) => ({
                              ...f,
                              gender: e.target.value,
                            }))
                          }
                        >
                          <option value="M">Male</option>
                          <option value="F">Female</option>
                          <option value="">Other</option>
                        </select>
                        <div className="flex gap-2">
                          <button
                            onClick={() => handleRegisterCrop(face, idx)}
                            className="btn-primary flex-1 text-xs py-1.5"
                          >
                            Register
                          </button>
                          <button
                            onClick={() => setRegisteringIdx(null)}
                            className="btn-secondary text-xs py-1.5"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="p-3">
                        <p className="text-xs text-slate-400 mb-2">
                          Unknown person
                        </p>
                        <button
                          onClick={() => setRegisteringIdx(idx)}
                          className="w-full btn-secondary text-xs py-1.5 flex items-center justify-center gap-1"
                        >
                          <UserPlus className="w-3 h-3" />
                          Register & Enroll
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Step 4: Done ──────────────────────────────────────────────── */}
      {step === "done" && (
        <div className="space-y-5">
          <div className="card bg-gradient-to-br from-brand-50 to-red-50 border-brand-200">
            <div className="flex items-center gap-4">
              <div className="w-14 h-14 bg-brand-600 rounded-2xl flex items-center justify-center shrink-0">
                <CheckCircle className="w-7 h-7 text-white" />
              </div>
              <div className="flex-1">
                <h2 className="font-bold text-brand-900 text-lg">
                  Attendance Recorded!
                </h2>
                <p className="text-brand-700 text-sm">
                  {summary?.present ?? "?"} / {summary?.total ?? "?"} students
                  present
                  {summary && (
                    <span className="ml-2 font-semibold">
                      ({(summary.progress * 100).toFixed(0)}%)
                    </span>
                  )}
                </p>
              </div>
              <a
                href={exportAttendance(selectedSession!.id)}
                download
                className="btn-secondary flex items-center gap-2 shrink-0"
              >
                <Download className="w-4 h-4" />
                CSV
              </a>
            </div>
            <div className="mt-4 bg-white/60 rounded-xl h-3 overflow-hidden">
              <div
                className="h-full bg-accent-600 transition-all rounded-xl"
                style={{ width: `${(summary?.progress ?? 0) * 100}%` }}
              />
            </div>
          </div>

          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-slate-900">Session Records</h3>
              <button
                onClick={() => {
                  setStep("setup");
                  setAnalysis(null);
                  setPreview(null);
                  setSelectedSession(null);
                  setConfirmedIds(new Set());
                }}
                className="btn-secondary text-sm"
              >
                New Session
              </button>
            </div>
            <div className="space-y-2">
              {attendance?.map((r, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between p-3 rounded-xl bg-slate-50 hover:bg-slate-100 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 bg-gradient-to-br from-brand-100 to-accent-100 rounded-full flex items-center justify-center">
                      <span className="text-xs font-bold text-brand-700">
                        {r.name[0]}
                      </span>
                    </div>
                    <span className="text-sm font-medium text-slate-900">
                      {r.name}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span
                      className={
                        r.status === "present"
                          ? "badge-present"
                          : "badge-absent"
                      }
                    >
                      {r.status}
                    </span>
                  </div>
                </div>
              ))}
              {(!attendance || attendance.length === 0) && (
                <p className="text-sm text-slate-400 text-center py-4">
                  No records yet
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
