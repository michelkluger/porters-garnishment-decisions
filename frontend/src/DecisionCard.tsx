import { ChevronDown, ExternalLink, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { Confidence, Decision, Route } from "./api";

// Pill styling copied from the status pill on withporters.com (sage). The amber and red variants
// are not in their palette: TODO(brand) confirm semantic colours with Porters.
const TONES = {
  good: { pill: "bg-[#E8EEEC] border-[#C4D4D0] text-[#3F6A5E]", dot: "bg-[#73968C]" },
  warn: { pill: "bg-[#F7F4F2] border-[#DCD6D1] text-[#7A5A1E]", dot: "bg-[#C08A2B]" },
  bad: { pill: "bg-[#FDECEE] border-[#F5B5BC] text-[#B00010]", dot: "bg-[#E40014]" },
  none: { pill: "bg-[#F2F2F2] border-[#E0E0E0] text-[#5B6168]", dot: "bg-[#99A1AF]" },
};
type Tone = keyof typeof TONES;

const ROUTES: Record<Route, [string, Tone]> = {
  auto: ["Auto", "good"],
  needs_human: ["Needs human", "warn"],
  reject: ["Reject", "bad"],
};
const CONFIDENCE: Record<Confidence, Tone> = { high: "good", low: "warn", invalid: "bad", absent: "none" };
const FIELD_LABELS: Record<string, string> = {
  debtor_name: "Debtor",
  amount: "Amount",
  case_reference: "Case reference",
  account_iban: "IBAN",
};

function Pill({ tone, children, large }: { tone: Tone; children: React.ReactNode; large?: boolean }) {
  return (
    <Badge variant="outline" className={cn("gap-1.5", large && "px-4 py-1.5 text-sm", TONES[tone].pill)}>
      <span className={cn("size-2 rounded-full", TONES[tone].dot)} aria-hidden />
      {children}
    </Badge>
  );
}

const Label = ({ children }: { children: React.ReactNode }) => (
  <p className="text-caption mb-2 text-xs font-medium tracking-widest uppercase">{children}</p>
);

export type Item = { key: string; fileName: string } & (
  | { state: "pending" }
  | { state: "error"; message: string }
  | { state: "done"; decision: Decision }
);

export function DecisionCard({ item }: { item: Item }) {
  return (
    <Card className="gap-5 rounded-3xl border-[#C5CBD3]/70 py-6 shadow-none">
      <CardHeader className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <CardTitle className="truncate text-lg font-medium">{item.fileName}</CardTitle>
          {item.state === "done" && (
            <CardDescription>
              {new Date(item.decision.created_at).toLocaleString()} · {item.decision.model} · rules v
              {item.decision.rules_version}
            </CardDescription>
          )}
        </div>
        {item.state === "done" && (
          <Pill tone={ROUTES[item.decision.route][1]} large>
            {ROUTES[item.decision.route][0]}
          </Pill>
        )}
      </CardHeader>

      <CardContent>
        {item.state === "pending" && (
          <p className="text-muted-foreground flex items-center gap-2" role="status">
            <Loader2 className="size-4 animate-spin" aria-hidden /> Reading the letter and applying the rules…
          </p>
        )}
        {item.state === "error" && (
          <p className="text-destructive" role="alert">
            {item.message}
          </p>
        )}
        {item.state === "done" && <DecisionBody decision={item.decision} />}
      </CardContent>

      {item.state === "done" && (
        <CardFooter className="text-muted-foreground flex-wrap gap-x-4 gap-y-1 border-t pt-4 text-xs">
          <span className="font-mono">{item.decision.id}</span>
          <a
            className="text-primary inline-flex items-center gap-1 hover:underline"
            href={`/api/decisions/${item.decision.id}`}
            target="_blank"
            rel="noreferrer"
          >
            Open stored record <ExternalLink className="size-3" aria-hidden />
          </a>
        </CardFooter>
      )}
    </Card>
  );
}

function DecisionBody({ decision }: { decision: Decision }) {
  const fields = Object.entries(decision.fields);
  const rules = [...decision.document_rules, ...fields.flatMap(([, f]) => f.rules)];

  return (
    <div className="space-y-6">
      <div>
        <Label>Why</Label>
        <ul className="space-y-1.5">
          {decision.reasons.map((reason) => {
            const [rule, detail] = reason.includes(": ") ? reason.split(/: (.*)/s) : [null, reason];
            return (
              <li key={reason} className="text-sm">
                {rule && <code className="bg-muted mr-2 rounded px-1.5 py-0.5 text-xs">{rule}</code>}
                {detail}
              </li>
            );
          })}
        </ul>
        {decision.error && <p className="text-muted-foreground mt-2 text-sm">Model error: {decision.error}</p>}
      </div>

      {fields.length > 0 && (
        <div>
          <Label>Extracted fields</Label>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Field</TableHead>
                <TableHead>Value</TableHead>
                <TableHead>Confidence</TableHead>
                <TableHead>Model said</TableHead>
                <TableHead>Source in letter</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {fields.map(([name, f]) => (
                <TableRow key={name}>
                  <TableCell className="font-medium">{FIELD_LABELS[name] ?? name}</TableCell>
                  <TableCell className="font-mono text-xs">{f.value ?? "—"}</TableCell>
                  <TableCell>
                    <Pill tone={CONFIDENCE[f.confidence]}>{f.confidence}</Pill>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{f.status}</TableCell>
                  <TableCell className="text-muted-foreground max-w-xs truncate" title={f.source_quote ?? ""}>
                    {f.source_quote ? `“${f.source_quote}”` : "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <Collapsible>
        <CollapsibleTrigger className="text-primary group inline-flex items-center gap-1 text-sm font-medium">
          Every rule evaluated ({rules.length})
          <ChevronDown className="size-4 transition-transform group-data-[state=open]:rotate-180" aria-hidden />
        </CollapsibleTrigger>
        <CollapsibleContent className="pt-3">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Rule</TableHead>
                <TableHead>Field</TableHead>
                <TableHead>Result</TableHead>
                <TableHead>Detail</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rules.map((r) => (
                <TableRow key={r.rule} className={cn(!r.fired && "text-muted-foreground")}>
                  <TableCell className="font-mono text-xs">{r.rule}</TableCell>
                  <TableCell>{r.field ? (FIELD_LABELS[r.field] ?? r.field) : "document"}</TableCell>
                  <TableCell>
                    {r.fired ? <Pill tone={ROUTES[r.route][1]}>fired → {ROUTES[r.route][0]}</Pill> : "passed"}
                  </TableCell>
                  <TableCell className="text-sm whitespace-normal">{r.detail}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}
