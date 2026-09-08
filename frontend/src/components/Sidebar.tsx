"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Camera,
  Users,
  BookOpen,
  BarChart3,
  GraduationCap,
} from "lucide-react";
import clsx from "clsx";

const NAV = [
  { href: "/", icon: LayoutDashboard, label: "Dashboard" },
  { href: "/attendance", icon: Camera, label: "Attendance" },
  { href: "/students", icon: Users, label: "Students" },
  { href: "/classes", icon: BookOpen, label: "Classes" },
  { href: "/reports", icon: BarChart3, label: "Reports" },
];

export default function Sidebar() {
  const path = usePathname();

  return (
    <aside className="w-64 bg-gradient-to-b from-white to-blue-50 border-r border-blue-200 flex flex-col h-full shrink-0">
      {/* Logo */}
      <div className="px-6 py-5 border-b border-blue-200">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-brand-600 rounded-xl flex items-center justify-center">
            <GraduationCap className="w-5 h-5 text-white" />
          </div>
          <div>
            <p className="font-bold text-slate-900 text-sm leading-tight">AttendEase</p>
            <p className="text-xs text-slate-400">Smart Attendance</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV.map(({ href, icon: Icon, label }) => {
          const active =
            href === "/" ? path === "/" : path.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={clsx(
                "flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all",
                active
                  ? "bg-brand-100 text-brand-700"
                  : "text-slate-500 hover:bg-blue-50 hover:text-slate-900"
              )}
            >
              <Icon
                className={clsx(
                  "w-4 h-4",
                  active ? "text-brand-600" : "text-slate-400"
                )}
              />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-4 py-4 border-t border-blue-200">
        <p className="text-xs text-slate-400 text-center">
          Powered by InsightFace AI
        </p>
      </div>
    </aside>
  );
}
