import ReactMarkdown from "react-markdown";
import type { QueryResponse, EvidenceRef } from "../types/api";
import ChartPanel from "./ChartPanel";

interface Props {
  response: QueryResponse | null;
}

const EVIDENCE_GLYPHS: Record<EvidenceRef["type"], string> = {
  bounding_box: "▢",
  overlay: "◇",
  heatmap: "▣",
  saliency: "◉",
  image_ref: "▣",
};

function EvidenceBadge({ evidence }: { evidence: EvidenceRef }) {
  return (
    <li className="flex items-start gap-3 rounded-lg border border-slate-800 bg-slate-950/60 p-2.5">
      <span className="mt-0.5 text-sm text-teal-400" aria-hidden="true">
        {EVIDENCE_GLYPHS[evidence.type]}
      </span>
      <div className="min-w-0">
        <span className="block text-[10px] font-semibold uppercase tracking-wider text-teal-400">
          {evidence.type.replace("_", " ")}
        </span>
        <span className="block text-[12px] leading-snug text-slate-400">{evidence.description}</span>
      </div>
    </li>
  );
}

export default function ResultsPanel({ response }: Props) {
  if (!response) return null;

  // Defensive: Gradio error paths may omit fields — never crash on .length
  const answer = typeof response.answer === "string" ? response.answer : "No answer returned.";
  const evidenceList = Array.isArray(response.evidence) ? response.evidence : [];
  // Prefer structured chart if present, else fallback to flat chart — question-aware
  const chart = response.structured?.chart ?? response.chart ?? [];
  const chartType =
    response.structured?.chart_type ??
    response.chart_type ??
    (response.execution_trace?.task === "count" ? "count" : "distribution");

  const wordCount = answer.split(/\s+/).length;

  return (
    <div className="space-y-4">
      {/* Answer — markdown bullets */}
      <section>
        <div className="mb-2 flex items-center gap-2.5">
          <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
            Result
          </span>
          <div className="divider flex-1" />
        </div>
        <div className="max-w-none text-[13px] leading-relaxed text-slate-200 [&_ol]:my-1 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:my-1 [&_ul]:my-1 [&_ul]:list-disc [&_ul]:pl-5 [&_li]:my-0.5">
          <ReactMarkdown>{answer}</ReactMarkdown>
        </div>
        <span className="text-[10px] tabular-nums text-slate-600">
          {wordCount} words · {answer.length} chars
        </span>
      </section>

      {/* Chart — bar/pie toggle, question-aware */}
      {chart.length > 0 && <ChartPanel chart={chart} chartType={chartType} />}

      {/* Evidence */}
      {evidenceList.length > 0 && (
        <section>
          <div className="mb-2 flex items-center gap-2.5">
            <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
              Evidence
            </span>
            <div className="divider flex-1" />
            <span className="text-[11px] tabular-nums text-slate-500">
              {evidenceList.length} item{evidenceList.length !== 1 ? "s" : ""}
            </span>
          </div>
          <ul className="grid gap-2">
            {evidenceList.map((ev, i) => (
              <EvidenceBadge key={i} evidence={ev} />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
