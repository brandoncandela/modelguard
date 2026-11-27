const P: Record<string, string> = {
  overview: "M3 13h8V3H3zm10 8h8V11h-8zM3 21h8v-6H3zm10-18v6h8V3z",
  inventory: "M4 6h16M4 12h16M4 18h10",
  monitoring: "M3 17l5-6 4 4 8-9",
  validation: "M9 12l2 2 4-4M7 3h10l4 4v14H3V3z",
  findings: "M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
  ai: "M9 3v2m6-2v2M9 19v2m6-2v2M3 9h2m-2 6h2m14-6h2m-2 6h2M7 5h10v14H7zm3 4h4v6h-4z",
  regulatory: "M12 3 3 7v2h18V7zM5 11v6m4-6v6m6-6v6m4-6v6M3 21h18",
  reporting: "M7 3h7l5 5v13H7zM14 3v5h5M10 13h6m-6 4h6",
  audit: "M12 8v4l3 2m6-2a9 9 0 1 1-18 0 9 9 0 0 1 18 0z",
};
export function Icon({ name, className = "h-4 w-4" }: { name: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d={P[name]} />
    </svg>
  );
}
