// @ts-nocheck
import { useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";
import type { ChartEntry } from "../types/api";

const COLORS = ["#38bdf8", "#22c55e", "#f59e0b", "#a78bfa", "#f43f5e", "#14b8a6"];

export default function ChartPanel({ chart, chartType }: { chart: ChartEntry[]; chartType?: string | null }) {
  const [mode, setMode] = useState<"bar" | "pie">("bar");
  if (!chart || chart.length === 0) return null;

  const isCount = chartType === "count";
  const data = chart.map((c) => ({ name: c.label, value: c.value }));

  const title = isCount ? "Count" : chartType === "change" ? "Change" : "Distribution";
  const unit = isCount ? "" : "%";
  return (
    <div className="border border-surface-400/30 bg-surface-800/40 rounded-lg p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[11px] font-medium text-ink-muted uppercase tracking-[0.1em]">
          {title} {isCount ? "(YOLO)" : "(measured)"}
        </span>
        <div className="flex gap-1">
          <button
            onClick={() => setMode("bar")}
            className={`px-2 py-1 text-[10px] rounded ${mode === "bar" ? "bg-accent text-white" : "bg-surface-700 text-ink-muted"}`}
          >
            Bar
          </button>
          <button
            onClick={() => setMode("pie")}
            className={`px-2 py-1 text-[10px] rounded ${mode === "pie" ? "bg-accent text-white" : "bg-surface-700 text-ink-muted"}`}
          >
            Pie
          </button>
        </div>
      </div>

      <div className="h-[180px]">
        <ResponsiveContainer width="100%" height="100%">
          {mode === "bar" ? (
            <BarChart data={data}>
              <XAxis dataKey="name" tick={{ fontSize: 10, fill: "#9ca3af" }} interval={0} angle={-20} dy={10} height={40} />
              <YAxis tick={{ fontSize: 10, fill: "#9ca3af" }} domain={isCount ? [0, "auto"] : [0, 100]} tickFormatter={(v) => `${v}${unit}`} />
              <Tooltip formatter={(v: number) => `${v}${unit}`} contentStyle={{ background: "#1e293b", border: "1px solid #334155", fontSize: 11 }} />
              <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                {data.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          ) : (
            <PieChart>
              <Pie data={data} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={70} label={(e) => `${e.name} ${e.value}${unit}`}>
                {data.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(v: number) => `${v}${unit}`} contentStyle={{ background: "#1e293b", border: "1px solid #334155", fontSize: 11 }} />
              <Legend wrapperStyle={{ fontSize: 10 }} />
            </PieChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
}
