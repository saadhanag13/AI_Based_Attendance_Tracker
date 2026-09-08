"use client";

import useSWR from "swr";
import Link from "next/link";
import { getClasses, getStudents } from "@/lib/api";
import { Class, Student } from "@/lib/types";
import {
  Users,
  BookOpen,
  Camera,
  BarChart3,
  ArrowRight,
  TrendingUp,
  CheckCircle,
} from "lucide-react";
import { format } from "date-fns";

const fetcher = (fn: () => Promise<unknown>) => fn();

export default function DashboardPage() {
  const { data: classes } = useSWR("classes", () => getClasses());
  const { data: students } = useSWR("students", () => getStudents());

  const today = format(new Date(), "EEEE, MMMM d, yyyy");

  const stats = [
    {
      label: "Total Classes",
      value: classes?.length ?? "—",
      icon: BookOpen,
      color: "bg-brand-50 text-brand-600",
      href: "/classes",
    },
    {
      label: "Registered Students",
      value: students?.length ?? "—",
      icon: Users,
      color: "bg-blue-50 text-accent-600",
      href: "/students",
    },
    {
      label: "Take Attendance",
      value: "Start →",
      icon: Camera,
      color: "bg-brand-50 text-brand-600",
      href: "/attendance",
    },
    {
      label: "View Reports",
      value: "Explore →",
      icon: BarChart3,
      color: "bg-red-50 text-brand-600",
      href: "/reports",
    },
  ];

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <p className="text-sm text-slate-400 font-medium">{today}</p>
        <h1 className="text-3xl font-bold text-slate-900 mt-1">
          Good morning! 👋
        </h1>
        <p className="text-slate-500 mt-1">
          Here&apos;s what&apos;s happening with your classes today.
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((s) => (
          <Link
            key={s.label}
            href={s.href}
            className="card hover:shadow-md transition-all group"
          >
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">
                  {s.label}
                </p>
                <p className="text-2xl font-bold text-slate-900 mt-2">
                  {s.value}
                </p>
              </div>
              <div className={`p-2 rounded-xl ${s.color}`}>
                <s.icon className="w-5 h-5" />
              </div>
            </div>
            <div className="mt-4 flex items-center text-brand-600 text-sm font-medium opacity-0 group-hover:opacity-100 transition-opacity">
              View <ArrowRight className="w-3 h-3 ml-1" />
            </div>
          </Link>
        ))}
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Classes List */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-slate-900">Your Classes</h2>
            <Link
              href="/classes"
              className="text-sm text-brand-600 hover:text-brand-700 font-medium"
            >
              Manage
            </Link>
          </div>
          <div className="space-y-2">
            {classes && classes.length > 0 ? (
              classes.slice(0, 5).map((cls: Class) => (
                <Link
                  key={cls.id}
                  href={`/attendance?class_id=${cls.id}`}
                  className="flex items-center justify-between p-3 rounded-xl hover:bg-slate-50 transition-colors group"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 bg-brand-100 rounded-lg flex items-center justify-center">
                      <BookOpen className="w-4 h-4 text-brand-600" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-slate-900">
                        {cls.name}
                      </p>
                      <p className="text-xs text-slate-400">
                        {cls.subject} · {cls.enrolled_count} students
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 text-xs text-brand-600 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Camera className="w-3 h-3" />
                    <span>Take</span>
                  </div>
                </Link>
              ))
            ) : (
              <div className="text-center py-8">
                <BookOpen className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                <p className="text-sm text-slate-400">No classes yet</p>
                <Link href="/classes" className="text-sm text-brand-600 mt-1 block">
                  Create your first class →
                </Link>
              </div>
            )}
          </div>
        </div>

        {/* How it works */}
        <div className="card bg-gradient-to-br from-brand-600 to-brand-700 text-white">
          <h2 className="font-semibold text-lg mb-4">How it works</h2>
          <div className="space-y-4">
            {[
              {
                step: "1",
                title: "Set up your class",
                desc: "Create a class and register students with photos.",
              },
              {
                step: "2",
                title: "Take a group photo",
                desc: "Upload or capture a photo of your class.",
              },
              {
                step: "3",
                title: "AI marks attendance",
                desc: "Faces are matched and attendance is recorded automatically.",
              },
              {
                step: "4",
                title: "Review & export",
                desc: "Confirm, correct, and download CSV reports.",
              },
            ].map((item) => (
              <div key={item.step} className="flex items-start gap-3">
                <div className="w-6 h-6 rounded-full bg-white/20 flex items-center justify-center text-xs font-bold shrink-0 mt-0.5">
                  {item.step}
                </div>
                <div>
                  <p className="text-sm font-medium">{item.title}</p>
                  <p className="text-xs text-brand-200">{item.desc}</p>
                </div>
              </div>
            ))}
          </div>
          <Link
            href="/attendance"
            className="mt-6 block text-center bg-white text-brand-700 font-semibold py-2.5 rounded-xl text-sm hover:bg-brand-50 transition-colors"
          >
            Start Taking Attendance
          </Link>
        </div>
      </div>

      {/* Recent Students */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold text-slate-900">Recently Registered Students</h2>
          <Link href="/students" className="text-sm text-brand-600 hover:text-brand-700 font-medium">
            View all
          </Link>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
          {students?.slice(0, 6).map((s: Student) => (
            <Link
              key={s.id}
              href={`/students/${s.id}`}
              className="flex flex-col items-center gap-2 p-3 rounded-xl hover:bg-slate-50 transition-colors"
            >
              <div className="w-12 h-12 rounded-full bg-brand-100 flex items-center justify-center overflow-hidden">
                <img
                  src={`/api/students/${s.id}/photo`}
                  alt={s.name}
                  className="w-full h-full object-cover"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = "none";
                  }}
                />
              </div>
              <p className="text-xs font-medium text-slate-700 text-center truncate w-full">
                {s.name.split(" ")[0]}
              </p>
            </Link>
          ))}
          {!students?.length && (
            <div className="col-span-full text-center py-6">
              <Users className="w-8 h-8 text-slate-300 mx-auto mb-2" />
              <p className="text-sm text-slate-400">No students registered yet</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
