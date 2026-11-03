import { ChevronDown, ExternalLink, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardFooter, CardHeader } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { Confidence, Decision } from "./api";
import { DecisionPath } from "./DecisionPath";
import { FIELD_LABELS, ROUTES, TONES, type Tone } from "./tones";

const CONFIDENCE: Record<Confidence, Tone> = { high: "good", low: "warn", invalid: "bad", absent: "none" };

// Two significant digits: a letter costs fractions of a cent, so a fixed number of decimals would show $0.00.
const usd = (n: number) => n.toLocaleString(undefined, { style: "currency", currency: "USD", maximumSignificantDigits: 2 });

function Stat({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="min-w-0 rounded-xl border border-[#C5CBD3]/70 px-4 py-3">
      <p className="text-muted-foreground text-xs">{label}</p>
      <p className="mt-1 truncate text-xl font-semibold tabular-nums" title={value}>
        {value}
      </p>
      <p className="text-muted-foreground mt-0.5 text-xs">{sub}</p>
    </div>
  );
}

// Which model read the letter, and what that call spent. A replayed (demo) reading made no call: estimate, marked ≈.
function ModelCall({ decision: d }: { decision: Decision }) {
  const colon = d.model.indexOf(":"); // "anthropic:claude-opus-5-5", "recorded:claude-haiku-5-5"
  const [source, name] = [d.model.slice(0, Math.max(colon, 0)), d.model.slice(colon + 1)];
  const recorded = source === "recorded";
  const approx = recorded ? "≈ " : "";
  const u = d.usage;
  const tokens = (n: number | undefined) => (n === undefined ? "—" : approx + n.toLocaleString());
  const retries = u && u.requests > 1 ? ` · ${u.requests} requests` : "";
  return (
    <div>
      <Label>Model call</Label>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat
          label="Model"
          value={name}
          sub={`${recorded ? "replayed" : source || "model"} · prompt ${d.prompt_version}`}
        />
        <Stat label="Input tokens" value={tokens(u?.input_tokens)} sub="prompt, schema and letter" />
        <Stat label="Output tokens" value={tokens(u?.output_tokens)} sub="the reading" />
        <Stat
          label="Cost"
          value={d.cost_usd == null ? "—" : approx + usd(d.cost_usd)}
          sub={
            d.cost_usd == null
              ? u
                ? "no price known for this model"
                : "no model call"
              : `${approx}${usd(d.cost_usd * 1000)} per 1,000 letters${retries}`
          }
        />
      </div>
      {recorded && u && (
        <p className="text-muted-foreground mt-2 text-xs">
          Demo estimate: no model was called. Tokens are counted at about 4 characters each and priced at {name}'s
          rates.
        </p>
      )}
    </div>
  );
}

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
  { state: "pending" } | { state: "error"; message: string } | { state: "done"; decision: Decision }
);

export function DecisionCard({ item }: { item: Item }) {
  return (
    <Collapsible defaultOpen>
      <Card className="gap-5 rounded-3xl border-[#C5CBD3]/70 py-6 shadow-none">
        <CardHeader className="block">
          {/* the whole header is the toggle; the file name and route stay visible when collapsed */}
          <CollapsibleTrigger className="group/card focus-visible:ring-ring/50 -m-2 flex w-[calc(100%+1rem)] flex-wrap items-start justify-between gap-3 rounded-xl p-2 text-left outline-none focus-visible:ring-[3px]">
            <span className="min-w-0">
              <span className="block truncate text-lg leading-none font-medium">{item.fileName}</span>
              {item.state === "done" && (
                <span className="text-muted-foreground mt-1.5 block text-sm">
                  {new Date(item.decision.created_at).toLocaleString()} · {item.decision.model} · rules v
                  {item.decision.rules_version}
                </span>
              )}
            </span>
            <span className="flex items-center gap-2">
              {item.state === "done" && (
                <Pill tone={ROUTES[item.decision.route][1]} large>
                  {ROUTES[item.decision.route][0]}
                </Pill>
              )}
              <ChevronDown
                className="text-muted-foreground size-5 transition-transform group-data-[state=open]/card:rotate-180"
                aria-hidden
              />
              <span className="sr-only">Show or hide details</span>
            </span>
          </CollapsibleTrigger>
        </CardHeader>

        <CollapsibleContent className="data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down flex flex-col gap-5 overflow-hidden">
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
        </CollapsibleContent>
      </Card>
    </Collapsible>
  );
}

function DecisionBody({ decision }: { decision: Decision }) {
  const fields = Object.entries(decision.fields);
  const rules = [...decision.document_rules, ...fields.flatMap(([, f]) => f.rules)];

  return (
    <div className="space-y-6">
      <div>
        <Label>Decision path</Label>
        <DecisionPath decision={decision} />
      </div>

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

      <ModelCall decision={decision} />

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
