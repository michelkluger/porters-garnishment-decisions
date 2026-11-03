import { RotateCcw } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { Decision, Route, RuleResult } from "./api";
import { FIELD_LABELS, ROUTES, TONES } from "./tones";

// Animated decision path: letter → model → one lane per field → its checks → the route each lane forces.
// The most severe route wins. Pure SVG + CSS keyframes (see index.css); the drawing scales to the card width.

const SEVERITY: Record<Route, number> = { auto: 0, needs_human: 1, reject: 2 };
const ORDER: Route[] = ["auto", "needs_human", "reject"];
const BLUE = "#1569e0"; // brand primary: data flowing through the pipeline
const BORDER = "#C5CBD3";

// Geometry in SVG units.
const W = 1000;
const PAD = 20;
const LANE_GAP = 12;
const CHIP = 24;
const X = { letter: 12, model: 168, field: 356, rules: 596, route: 850 };
const NW = { letter: 120, model: 144, field: 204, rules: 214, route: 138 };
const ROUTE_H = 46;
const ROUTE_GAP = 16;

// Timeline in seconds.
const T = { edge1: 0.25, model: 0.5, lanes: 0.8, step: 0.14 };

type Lane = { key: string; label: string; value: string; rules: RuleResult[]; fired: RuleResult[]; route: Route };
type Row = Lane & { y: number; h: number; cy: number };

const worst = (rules: RuleResult[]) =>
  rules.reduce<Route>((acc, r) => (r.fired && SEVERITY[r.route] > SEVERITY[acc] ? r.route : acc), "auto");
const clip = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);
const curve = (x1: number, y1: number, x2: number, y2: number) => {
  const mx = (x1 + x2) / 2;
  return `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`;
};

const fade = (t: number) => ({ animation: `dp-in .35s ease-out ${t}s both` });
const draw = (t: number) => ({ animation: `dp-draw .45s ease-out ${t}s both` });
const flow = (t: number) => ({ animation: `dp-in .2s linear ${t}s both, dp-flow .9s linear ${t}s infinite` });
const dim = (t: number) => ({ animation: `dp-dim .5s ease-out ${t}s both` });

function toLanes(d: Decision): Lane[] {
  const lane = (key: string, label: string, value: string, rules: RuleResult[]): Lane => ({
    key, label, value, rules, fired: rules.filter((r) => r.fired), route: worst(rules),
  });
  if (!d.extraction) return [lane("extraction", "Extraction", "failed", d.document_rules)];
  const currency = d.extraction.amount.currency;
  return [
    lane("document", "Document type", d.extraction.document_type.replaceAll("_", " "), d.document_rules),
    ...Object.entries(d.fields).map(([key, f]) =>
      lane(key, FIELD_LABELS[key] ?? key, f.value == null ? "absent" : key === "amount" && currency ? `${currency} ${f.value}` : f.value, f.rules),
    ),
  ];
}

const laneHeight = (l: Lane) => Math.max(54, 36 + l.fired.length * CHIP);

function layout(lanes: Lane[]) {
  const lanesH = lanes.reduce((sum, l) => sum + laneHeight(l), 0) + LANE_GAP * (lanes.length - 1);
  const routesH = 3 * ROUTE_H + 2 * ROUTE_GAP;
  const H = Math.max(lanesH, routesH + 28) + 2 * PAD;
  let y = (H - lanesH) / 2;
  const rows: Row[] = lanes.map((l) => {
    const h = laneHeight(l);
    const row = { ...l, y, h, cy: y + h / 2 };
    y += h + LANE_GAP;
    return row;
  });
  const cy = H / 2;
  const top = cy - routesH / 2 + 10;
  const routeY = Object.fromEntries(ORDER.map((r, i) => [r, top + i * (ROUTE_H + ROUTE_GAP)])) as Record<Route, number>;
  return { rows, H, cy, routeY };
}

function Edge({ d, t, color, strong }: { d: string; t: number; color: string; strong: boolean }) {
  return (
    <g>
      <path d={d} pathLength={1} strokeDasharray="1" fill="none" stroke={color} strokeWidth={strong ? 2.25 : 1.25}
        strokeOpacity={strong ? 1 : 0.4} className="dp-anim" style={draw(t)} />
      {strong && (
        <path d={d} fill="none" stroke="white" strokeWidth={2.25} strokeDasharray="3 9" strokeLinecap="round"
          className="dp-anim dp-flow" style={flow(t + 0.45)} />
      )}
    </g>
  );
}

function Node(props: { x: number; y: number; w: number; h: number; t: number; title: string; stroke?: string; fill?: string; children: React.ReactNode }) {
  const { x, y, w, h, t, title, stroke = BORDER, fill = "white", children } = props;
  return (
    <g className="dp-anim" style={fade(t)}>
      <title>{title}</title>
      <rect x={x} y={y} width={w} height={h} rx={14} fill={fill} stroke={stroke} />
      {children}
    </g>
  );
}

const Caption = ({ x, y, children }: { x: number; y: number; children: React.ReactNode }) => (
  <text x={x} y={y} className="fill-caption text-[10px] font-medium tracking-widest uppercase">{children}</text>
);

export function DecisionPath({ decision }: { decision: Decision }) {
  const [run, setRun] = useState(0);
  const lanes = toLanes(decision);
  const { rows, H, cy, routeY } = layout(lanes);
  const tRoutes = T.lanes + rows.length * T.step + 1.1;
  const tVerdict = tRoutes + 0.45 + rows.length * T.step + 0.3;
  const summary = `Decision path. ${rows.map((l) => `${l.label}: ${ROUTES[l.route][0]}`).join("; ")}. Final route: ${ROUTES[decision.route][0]}, the most severe.`;

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto rounded-2xl border border-[#C5CBD3]/60 bg-[#F8FAFB]">
        <svg key={run} viewBox={`0 0 ${W} ${H}`} className="h-auto w-full min-w-[720px]" role="img" aria-label={summary}>
          {/* letter */}
          <Node x={X.letter} y={cy - 32} w={NW.letter} h={64} t={0} title="The uploaded letter">
            <Caption x={X.letter + 14} y={cy - 7}>Letter</Caption>
            <text x={X.letter + 14} y={cy + 13} className="fill-foreground text-[12px]">{decision.letter_text.length} chars</text>
          </Node>
          <Edge d={`M${X.letter + NW.letter},${cy} H${X.model}`} t={T.edge1} color={BLUE} strong />

          {/* model */}
          <Node x={X.model} y={cy - 38} w={NW.model} h={76} t={T.model} title={`Model: ${decision.model}`}>
            <Caption x={X.model + 14} y={cy - 13}>LLM extraction</Caption>
            <text x={X.model + 14} y={cy + 6} className="fill-foreground font-mono text-[11px]">{clip(decision.model.replace(/^.*:/, ""), 19)}</text>
            <text x={X.model + 14} y={cy + 23} className="fill-muted-foreground text-[10px]">
              {decision.model.startsWith("recorded:") ? "recorded run, replayed" : "reads, never decides"}
            </text>
          </Node>

          {/* one lane per field */}
          {rows.map((l, i) => {
            const t0 = T.lanes + i * T.step;
            const tone = TONES[ROUTES[l.route][1]];
            const passed = l.rules.length - l.fired.length;
            return (
              <g key={l.key}>
                <Edge d={curve(X.model + NW.model, cy, X.field, l.cy)} t={t0} color={BLUE} strong />
                <Node x={X.field} y={l.y} w={NW.field} h={l.h} t={t0 + 0.3} title={`${l.label}: ${l.value}`}>
                  <Caption x={X.field + 14} y={l.cy - 4}>{l.label}</Caption>
                  <text x={X.field + 14} y={l.cy + 14} className="fill-foreground font-mono text-[12px]">{clip(l.value, 26)}</text>
                </Node>
                <Edge d={`M${X.field + NW.field},${l.cy} H${X.rules}`} t={t0 + 0.55} color={BLUE} strong />
                <Node x={X.rules} y={l.y} w={NW.rules} h={l.h} t={t0 + 0.75} stroke={tone.line}
                  fill={l.fired.length ? tone.soft : "white"} title={l.rules.map((r) => `${r.fired ? "FIRED" : "passed"} ${r.rule}: ${r.detail}`).join("\n")}>
                  <text x={X.rules + 14} y={l.fired.length ? l.y + 20 : l.cy + 4} className="text-[11px] font-medium" fill={tone.ink}>
                    {l.fired.length ? `${passed}/${l.rules.length} checks passed` : `all ${l.rules.length} checks passed`}
                  </text>
                  {l.fired.map((r, j) => {
                    const c = TONES[ROUTES[r.route][1]];
                    return (
                      <g key={r.rule} className="dp-anim" style={fade(t0 + 0.95 + j * 0.1)}>
                        <title>{`${r.rule}: ${r.detail}`}</title>
                        <rect x={X.rules + 10} y={l.y + 28 + j * CHIP} width={NW.rules - 20} height={20} rx={10} fill="white" stroke={c.line} />
                        <text x={X.rules + 20} y={l.y + 42 + j * CHIP} className="font-mono text-[10px]" fill={c.ink}>{clip(r.rule, 30)}</text>
                      </g>
                    );
                  })}
                </Node>
                <Edge d={curve(X.rules + NW.rules, l.cy, X.route, routeY[l.route] + ROUTE_H / 2)}
                  t={tRoutes + 0.45 + i * T.step} color={tone.line} strong={l.route === decision.route} />
              </g>
            );
          })}

          {/* routes: every lane points at one; the most severe one wins */}
          <g className="dp-anim" style={fade(tRoutes)}>
            <Caption x={X.route} y={routeY.auto - 12}>Most severe wins</Caption>
          </g>
          {ORDER.map((r) => {
            const tone = TONES[ROUTES[r][1]];
            const chosen = r === decision.route;
            const y = routeY[r];
            return (
              <g key={r} className="dp-anim" style={fade(tRoutes)}>
                <g opacity={chosen ? 1 : 0.35} className="dp-anim" style={chosen ? undefined : dim(tVerdict)}>
                  <rect x={X.route} y={y} width={NW.route} height={ROUTE_H} rx={ROUTE_H / 2} fill="white" stroke={BORDER} />
                  {chosen && (
                    <rect x={X.route} y={y} width={NW.route} height={ROUTE_H} rx={ROUTE_H / 2} fill={tone.soft}
                      stroke={tone.line} strokeWidth={2.5} className="dp-anim" style={fade(tVerdict)} />
                  )}
                  <circle cx={X.route + 22} cy={y + ROUTE_H / 2} r={5} fill={tone.line} />
                  <text x={X.route + 36} y={y + ROUTE_H / 2 + 5} className="text-[13px] font-medium" fill={chosen ? tone.ink : "#5B6168"}>
                    {ROUTES[r][0]}
                  </text>
                </g>
              </g>
            );
          })}
        </svg>
      </div>
      <div className="text-muted-foreground flex flex-wrap items-center justify-between gap-2 text-xs">
        <span>
          Each field's checks send it to a route; the most severe wins (reject › needs human › auto). Hover a node for
          its rules.
        </span>
        <Button variant="ghost" size="sm" className="h-7 rounded-full text-xs" onClick={() => setRun((n) => n + 1)}>
          <RotateCcw className="size-3.5" aria-hidden /> Replay
        </Button>
      </div>
    </div>
  );
}
