import { useEffect, useRef } from "react";

// Plotly is loaded on demand so the initial bundle stays small.
let plotly: Promise<any> | null = null;
const load = () => (plotly ??= import("plotly.js-dist-min").then((m: any) => m.default ?? m));

export const COLORS = { accent: "#1E4DB7", teal: "#0F766E", amber: "#B45309", orange: "#EA580C", red: "#B91C1C", slate: "#94A3B8", light: "#93C5FD" };

export function Plot({ data, layout, height = 260, ariaLabel }: { data: any[]; layout?: any; height?: number; ariaLabel: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let alive = true;
    const el = ref.current;
    load().then((P) => {
      if (!alive || !el) return;
      P.react(el, data, {
        height, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
        font: { family: "Inter, system-ui, sans-serif", size: 11, color: "#334155" },
        xaxis: { gridcolor: "#EEF2F7", linecolor: "#CBD5E1", tickfont: { size: 10.5 }, automargin: true },
        yaxis: { gridcolor: "#EEF2F7", linecolor: "#CBD5E1", zeroline: false, tickfont: { size: 10.5 }, automargin: true },
        legend: { orientation: "h", y: 1.02, yanchor: "bottom", x: 1, xanchor: "right", font: { size: 10.5 } }, hoverlabel: { font: { size: 11 } },
        margin: { l: 44, r: 12, t: 28, b: 36 },
        ...layout,
      }, { displayModeBar: false, responsive: true });
    });
    return () => { alive = false; };
  }, [data, layout, height]);
  useEffect(() => () => { if (ref.current) load().then((P) => ref.current && P.purge(ref.current)); }, []);
  return <div ref={ref} role="img" aria-label={ariaLabel} style={{ minHeight: height }} />;
}

/** Category x-axis for monthly periods (prevents Plotly from treating "2026-10" as a date). */
export const periodAxis = { type: "category", gridcolor: "#EEF2F7", linecolor: "#CBD5E1", tickfont: { size: 10.5 }, automargin: true };

/** Grey band behind the reference window, in category units. */
export function refBand(count: number) {
  if (!count) return [];
  return [{ type: "rect", xref: "x", yref: "paper", x0: -0.5, x1: count - 0.5, y0: 0, y1: 1, fillcolor: "#E2E8F0", opacity: 0.35,
    line: { width: 0 }, layer: "below" }];
}
