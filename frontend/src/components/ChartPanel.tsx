import { useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import type { ChartEntry } from "../types/api";

/** High-contrast series colours that read clearly on a slate-950 canvas. */
const COLORS = ["#2dd4bf", "#38bdf8", "#a78bfa", "#fbbf24", "#fb7185", "#34d399"];
const NEGATIVE = "#fb7185";
const POSITIVE = "#2dd4bf";

type Datum = { name: string; value: number };

const TOOLTIP_STYLE = {
  backgroundColor: "#0f172a",
  border: "1px solid #334155",
  borderRadius: 8,
  fontSize: 12,
  color: "#e2e8f0",
  boxShadow: "0 10px 25px -5px rgb(0 0 0 / 0.6)",
} satisfies React.CSSProperties;

const AXIS_TICK = { fontSize: 10, fill: "#94a3b8" } as const;

/** Keeps long category names from colliding with the neighbouring axis ticks. */
function truncateLabel(value: string): string {
  return value.length > 12 ? `${value.slice(0, 11)}…` : value;
}

function formatValue(value: number, unit: string): string {
  return `${value}${unit}`;
}

interface Props {
  chart: ChartEntry[];
  chartType?: string | null;
}

export default function ChartPanel({ chart, chartType }: Props) {
  const [mode, setMode] = useState<"bar" | "pie">("bar");
  if (!chart || chart.length === 0) return null;

  const isCount = chartType === "count";
  const isChange = chartType === "change";
  const unit = isCount ? "" : "%";
  const title = isCount ? "Count" : isChange ? "Change" : "Distribution";
  const subtitle = isCount ? "(YOLO)" : isChange ? "(delta T2-T1)" : "(measured)";

  const data: Datum[] = chart.map((entry) => ({ name: entry.label, value: entry.value }));
  const pieData: Datum[] = data.map((d) => ({ ...d, value: Math.abs(d.value) }));
  const pieTotal = pieData.reduce((sum, d) => sum + d.value, 0);

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <span className="text-[11px] font-medium uppercase tracking-[0.1em] text-slate-500">
          {title} {subtitle}
        </span>
        <div
          role="group"
          aria-label="Chart type"
          className="flex gap-1 rounded-md border border-slate-800 bg-slate-950 p-0.5"
        >
          {(["bar", "pie"] as const).map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setMode(option)}
              aria-pressed={mode === option}
              className={[
                "rounded px-2 py-1 text-[10px] font-semibold uppercase tracking-wider",
                "transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/50",
                mode === option
                  ? "bg-teal-500/15 text-teal-300"
                  : "text-slate-500 hover:text-slate-300",
              ].join(" ")}
            >
              {option}
            </button>
          ))}
        </div>
      </div>

      <div className="h-[220px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          {mode === "bar" ? (
            <BarChart data={data} margin={{ top: 4, right: 4, bottom: 4, left: -18 }}>
              <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="name"
                tick={AXIS_TICK}
                tickFormatter={truncateLabel}
                tickLine={false}
                axisLine={{ stroke: "#1e293b" }}
                interval={0}
                height={32}
              />
              <YAxis
                tick={AXIS_TICK}
                tickLine={false}
                axisLine={false}
                width={52}
                domain={isChange ? [-100, 100] : isCount ? [0, "auto"] : [0, 100]}
                tickFormatter={(v: number) => formatValue(v, unit)}
              />
              <Tooltip
                cursor={{ fill: "rgba(45, 212, 191, 0.08)" }}
                formatter={(v: number) => formatValue(v, unit)}
                contentStyle={TOOLTIP_STYLE}
                labelStyle={{ color: "#94a3b8", marginBottom: 4 }}
                itemStyle={{ color: "#e2e8f0" }}
              />
              <Bar dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={56}>
                {data.map((entry, i) => (
                  <Cell
                    key={i}
                    fill={
                      isChange
                        ? entry.value < 0
                          ? NEGATIVE
                          : POSITIVE
                        : COLORS[i % COLORS.length]
                    }
                  />
                ))}
              </Bar>
            </BarChart>
          ) : (
            <PieChart>
              <Pie
                data={pieData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={78}
                innerRadius={44}
                paddingAngle={1.5}
                stroke="none"
                isAnimationActive={false}
              >
                {pieData.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip
                formatter={(v: number) => formatValue(v, unit)}
                contentStyle={TOOLTIP_STYLE}
                labelStyle={{ color: "#94a3b8", marginBottom: 4 }}
                itemStyle={{ color: "#e2e8f0" }}
              />
            </PieChart>
          )}
        </ResponsiveContainer>
      </div>

      {/* Legend sits below the canvas — never on top of the shapes. */}
      {mode === "pie" && pieTotal > 0 ? (
        <ul className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-slate-800 pt-3">
          {pieData.map((entry, i) => (
            <li key={i} className="flex items-center gap-1.5 text-[11px] text-slate-400">
              <span
                className="h-2 w-2 flex-shrink-0 rounded-full"
                style={{ backgroundColor: COLORS[i % COLORS.length] }}
                aria-hidden="true"
              />
              <span className="text-slate-300">{entry.name}</span>
              <span className="tabular-nums text-slate-500">
                {((entry.value / pieTotal) * 100).toFixed(1)}%
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
