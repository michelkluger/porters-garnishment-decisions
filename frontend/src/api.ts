// Mirrors the backend's DecisionResponse (backend/app/decisions/schema.py).
export type Route = "auto" | "needs_human" | "reject";
export type Confidence = "high" | "low" | "invalid" | "absent";

export interface RuleResult {
  rule: string;
  field: string | null;
  fired: boolean;
  route: Route;
  detail: string;
}

export interface FieldEvidence {
  value: string | null;
  source_quote: string | null;
  status: string;
  confidence: Confidence;
  rules: RuleResult[];
}

export interface Decision {
  id: string;
  created_at: string;
  route: Route;
  primary_rule: string;
  reasons: string[];
  fields: Record<string, FieldEvidence>;
  document_rules: RuleResult[];
  rules_version: string;
  letter_text: string;
  extraction: { document_type: string; amount: { currency: string | null } } | null; // only what the UI reads
  model: string;
  prompt_version: string;
  error: string | null;
}

export async function submitLetter(text: string): Promise<Decision> {
  const res = await fetch("/api/decisions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = body?.detail;
    const message = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((d) => d.msg).join("; ") : null;
    throw new Error(message ?? `Request failed (HTTP ${res.status})`);
  }
  return body;
}
