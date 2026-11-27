import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { ErrorBox } from "../components/ui";
import { Logo } from "../components/layout/AppShell";

const DEMO = [
  { u: "admin", r: "Administrator", d: "Avery Collins, Model Risk Technology" },
  { u: "jpatel", r: "Model Owner", d: "Jordan Patel, Transaction Monitoring Analytics" },
  { u: "nbrooks", r: "Validator", d: "Nadia Brooks, Lead Model Validator" },
  { u: "hmarsh", r: "Compliance Reviewer", d: "Helen Marsh, Head of Model Risk Management" },
];

export default function Login() {
  const { login, user } = useAuth();
  const nav = useNavigate();
  const loc = useLocation() as any;
  const [username, setUsername] = useState("hmarsh");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to={loc.state?.from ?? "/"} replace />;
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await login(username, password);
      nav(loc.state?.from ?? "/", { replace: true });
    } catch (x) {
      setErr(x);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="flex min-h-full items-center justify-center p-4">
      <div className="grid w-full max-w-4xl gap-6 md:grid-cols-[1fr_1.1fr]">
        <div className="flex flex-col justify-center gap-4">
          <Logo />
          <h1 className="text-[22px] font-semibold leading-tight">Financial crime model risk management and AI governance</h1>
          <p className="text-[13px] text-muted">Inventory, monitoring, validation, findings, AI governance, regulatory control mapping and committee reporting for a fictional international bank. All data is synthetic.</p>
          <ul className="space-y-1 text-[12.5px] text-muted">
            <li>Metrics computed from 181,000 scored records across ten models</li>
            <li>Hash-chained, append-only audit trail</li>
            <li>Assessments are internal governance tools, not certifications</li>
          </ul>
        </div>
        <form onSubmit={submit} className="panel space-y-4 p-6">
          <div>
            <h2 className="text-[15px] font-semibold">Sign in</h2>
            <p className="text-[12px] text-muted">Demo users share the password set by MODELGUARD_DEMO_PASSWORD when the database was seeded.</p>
          </div>
          <div className="grid gap-2">
            {DEMO.map((d) => (
              <button type="button" key={d.u} onClick={() => setUsername(d.u)}
                className={`flex items-center justify-between rounded-md border px-3 py-2 text-left ${username === d.u ? "border-accent bg-accent-soft" : "border-line hover:bg-sunken"}`}>
                <span><span className="font-medium">{d.u}</span><span className="block text-[11.5px] text-muted">{d.d}</span></span>
                <span className="text-[11px] text-muted">{d.r}</span>
              </button>
            ))}
          </div>
          <label className="block"><span className="label">Username</span>
            <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" /></label>
          <label className="block"><span className="label">Password</span>
            <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></label>
          <ErrorBox error={err} />
          <button className="btn-primary w-full justify-center" disabled={busy || !password}>{busy ? "Signing in" : "Sign in"}</button>
        </form>
      </div>
    </div>
  );
}
