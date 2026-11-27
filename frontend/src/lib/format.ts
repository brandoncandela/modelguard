export const pct = (v?: number | null, d = 1) => (v === null || v === undefined ? "–" : `${(v * 100).toFixed(d)}%`);
export const num = (v?: number | null, d = 0) =>
  v === null || v === undefined ? "–" : v.toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d });
export const dec = (v?: number | null, d = 3) => (v === null || v === undefined ? "–" : v.toFixed(d));
export function date(v?: string | null) {
  if (!v) return "–";
  const d = new Date(v.length === 10 ? `${v}T00:00:00` : v);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}
export function dateTime(v?: string | null) {
  if (!v) return "–";
  return new Date(v).toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}
export const metricLabel: Record<string, string> = {
  precision: "Precision", recall: "Recall", f1: "F1 score", false_positive_rate: "False-positive rate",
  alert_rate: "Alert rate", alert_conversion_rate: "Alert conversion", override_rate: "Override rate",
  psi: "Score PSI", max_feature_psi: "Max feature PSI", dq_exception_rate: "DQ exceptions",
  factual_accuracy: "Factual accuracy", hallucination_rate: "Hallucination rate",
  unsupported_claim_rate: "Unsupported claims", policy_compliance: "Policy compliance",
  response_consistency: "Consistency",
};
export const isRate = (m: string) => !["psi", "max_feature_psi"].includes(m);
export const fmtMetric = (m: string, v?: number | null) => (isRate(m) ? pct(v) : dec(v));
