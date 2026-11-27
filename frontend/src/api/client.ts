// Thin fetch wrapper: bearer token, JSON or multipart bodies, and the API's error envelope.
const BASE = "/api/v1";
const KEY = "modelguard.token";

let token: string | null = null;
try {
  token = sessionStorage.getItem(KEY);
} catch {
  token = null;
}

export function setToken(t: string | null) {
  token = t;
  try {
    if (t) sessionStorage.setItem(KEY, t);
    else sessionStorage.removeItem(KEY);
  } catch {
    /* storage unavailable: keep the token in memory only */
  }
}
export const getToken = () => token;

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown,
              public requestId?: string) {
    super(message);
  }
}

type Query = Record<string, string | number | boolean | string[] | undefined | null>;

function qs(query?: Query) {
  if (!query) return "";
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => p.append(k, x));
    else p.append(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown; form?: FormData; query?: Query } = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const res = await fetch(`${BASE}${path}${qs(opts.query)}`, { method: opts.method ?? (body ? "POST" : "GET"), headers, body });
  if (res.status === 401 && token) {
    setToken(null);
    window.dispatchEvent(new Event("modelguard:unauthorized"));
  }
  if (!res.ok) {
    let err: any = {};
    try {
      err = (await res.json()).error ?? {};
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(res.status, err.code ?? "error", err.message ?? res.statusText, err.details, err.request_id);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export async function download(path: string, fallbackName: string) {
  const res = await fetch(`${BASE}${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!res.ok) throw new ApiError(res.status, "download_failed", "Download failed");
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") ?? "";
  const name = /filename="?([^";]+)"?/.exec(cd)?.[1] ?? fallbackName;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const d = e.details as any;
    if (e.code === "validation_error" && Array.isArray(d))
      return d.map((x: any) => `${(x.loc ?? []).slice(-1)[0]}: ${x.msg}`).join("; ");
    if (d?.findings) return `${e.message} (${d.findings.join(", ")})`;
    return e.message;
  }
  return e instanceof Error ? e.message : String(e);
}
