import type { Route } from "./api";

// Pill styling copied from the status pill on withporters.com (sage). The amber and red variants
// are not in their palette: TODO(brand) confirm semantic colours with Porters.
// Class strings for HTML (Tailwind needs them literal), hex values for SVG.
export const TONES = {
  good: { pill: "bg-[#E8EEEC] border-[#C4D4D0] text-[#3F6A5E]", dot: "bg-[#73968C]", line: "#73968C", soft: "#E8EEEC", ink: "#3F6A5E" },
  warn: { pill: "bg-[#F7F4F2] border-[#DCD6D1] text-[#7A5A1E]", dot: "bg-[#C08A2B]", line: "#C08A2B", soft: "#F7F4F2", ink: "#7A5A1E" },
  bad: { pill: "bg-[#FDECEE] border-[#F5B5BC] text-[#B00010]", dot: "bg-[#E40014]", line: "#E40014", soft: "#FDECEE", ink: "#B00010" },
  none: { pill: "bg-[#F2F2F2] border-[#E0E0E0] text-[#5B6168]", dot: "bg-[#99A1AF]", line: "#99A1AF", soft: "#F2F2F2", ink: "#5B6168" },
};
export type Tone = keyof typeof TONES;

export const ROUTES: Record<Route, [string, Tone]> = {
  auto: ["Auto", "good"],
  needs_human: ["Needs human", "warn"],
  reject: ["Reject", "bad"],
};

export const FIELD_LABELS: Record<string, string> = {
  debtor_name: "Debtor",
  amount: "Amount",
  case_reference: "Case reference",
  account_iban: "IBAN",
};
