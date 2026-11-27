import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../../auth/AuthContext";
import { api } from "../../api/client";
import { Icon } from "./Icon";
import { date } from "../../lib/format";

export const NAV = [
  { to: "/", label: "Executive Overview", icon: "overview" },
  { to: "/inventory", label: "Model Inventory", icon: "inventory" },
  { to: "/monitoring", label: "Performance Monitoring", icon: "monitoring" },
  { to: "/validations", label: "Validation Management", icon: "validation" },
  { to: "/findings", label: "Findings & Remediation", icon: "findings" },
  { to: "/ai", label: "AI Governance", icon: "ai" },
  { to: "/regulatory", label: "Regulatory Controls", icon: "regulatory" },
  { to: "/reporting", label: "Committee Reporting", icon: "reporting" },
  { to: "/audit", label: "Audit Trail", icon: "audit", perm: "audit:read" },
];

export function Logo() {
  return (
    <div className="flex items-center gap-2">
      <svg viewBox="0 0 32 32" className="h-6 w-6" aria-hidden="true"><path d="M16 2 4 7v8c0 7.2 5 13.4 12 15 7-1.6 12-7.8 12-15V7z" fill="rgb(var(--accent))" /><path d="m10.5 16 4 4 7-8" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
      <span className="text-[15px] font-semibold tracking-tight">ModelGuard</span>
    </div>
  );
}

export default function AppShell() {
  const { user, logout, can } = useAuth();
  const loc = useLocation();
  const [open, setOpen] = useState(false);
  const health = useQuery({ queryKey: ["health"], queryFn: () => api("/health"), staleTime: 60_000 });
  const dash = useQuery({ queryKey: ["asof"], queryFn: () => api("/dashboard/trends"), staleTime: 60_000 });
  const lastPeriod = dash.data?.periods?.slice(-1)[0];
  const current = NAV.find((n) => (n.to === "/" ? loc.pathname === "/" : loc.pathname.startsWith(n.to)));

  const nav = (
    <nav className="flex flex-col gap-0.5 p-2" aria-label="Main">
      {NAV.filter((n) => !n.perm || can(n.perm)).map((n) => (
        <NavLink key={n.to} to={n.to} end={n.to === "/"} onClick={() => setOpen(false)}
          className={({ isActive }) => `flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[12.5px] font-medium ${isActive ? "bg-accent-soft text-accent" : "text-muted hover:bg-sunken hover:text-ink"}`}>
          <Icon name={n.icon} />{n.label}
        </NavLink>
      ))}
    </nav>
  );

  return (
    <div className="flex h-full">
      <aside className="hidden w-60 shrink-0 flex-col border-r border-line bg-surface lg:flex">
        <div className="flex h-14 items-center border-b border-line px-4"><Logo /></div>
        <div className="flex-1 overflow-y-auto">{nav}</div>
        <div className="border-t border-line p-3 text-[11px] leading-4 text-muted">
          Candela Bank is fictional. All data is synthetic. Assessments are internal governance tools, not certifications.
        </div>
      </aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/30" onClick={() => setOpen(false)} />
          <aside className="relative h-full w-64 bg-surface shadow-xl">
            <div className="flex h-14 items-center border-b border-line px-4"><Logo /></div>{nav}
          </aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line bg-surface px-4">
          <button className="btn-ghost h-8 px-2 lg:hidden" onClick={() => setOpen(true)} aria-label="Open navigation">Menu</button>
          <h1 className="truncate text-[15px] font-semibold">{current?.label ?? "ModelGuard"}</h1>
          <div className="ml-auto flex items-center gap-3 text-[12px] text-muted">
            <span className="hidden md:inline">Candela Bank (fictional)</span>
            {lastPeriod && <span className="hidden sm:inline rounded border border-line px-2 py-0.5">Data to {lastPeriod.period}</span>}
            {health.data?.as_of && <span className="hidden sm:inline">As of {date(health.data.as_of)}</span>}
            <span className={`hidden h-2 w-2 rounded-full sm:inline-block ${health.isSuccess ? "bg-ok" : "bg-warn"}`} title={health.isSuccess ? `API ok (${health.data?.database})` : "API unreachable"} />
            {user && (
              <div className="flex items-center gap-2 border-l border-line pl-3">
                <div className="hidden text-right leading-4 sm:block">
                  <div className="text-[12.5px] font-medium text-ink">{user.full_name}</div>
                  <div className="text-[11px]">{user.role_label}</div>
                </div>
                <button className="btn-ghost h-7 px-2" onClick={logout}>Sign out</button>
              </div>
            )}
          </div>
        </header>
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[1440px] p-4 lg:p-5"><Outlet /></div>
        </main>
      </div>
    </div>
  );
}
