// @ts-nocheck
import ReactMarkdown from "react-markdown";
import type { QueryResponse, EvidenceRef } from "../types/api";
import ChartPanel from "./ChartPanel";

interface Props {
  response: QueryResponse | null;
}

function EvidenceBadge({ evidence }: { evidence: EvidenceRef }) {
  const icons: Record<EvidenceRef["type"], string> = {
    bounding_box: "\u25A2",
    overlay: "\u25C8",
    heatmap: "\u25A3",
    saliency: "\u25CE",
    image_ref: "\u25A3",
  };

  return (
    <div className="flex items-start gap-3 px-3 py-2.5 border border-surface-400/30 bg-surface-700/20 rounded-lg">
      <span className="text-accent text-sm mt-0.5">{icons[evidence.type]}</span>
      <div className="min-w-0">
        <span className="text-[11px] font-medium text-accent block">
          {evidence.type.replace("_", " ").toUpperCase()}
        </span>
        <span className="text-[12px] text-ink-secondary leading-snug">{evidence.description}</span>
      </div>
    </div>
  );
}

export default function ResultsPanel({ response }: Props) {
  if (!response) return null;

  // Prefer structured chart if present, else fallback to flat chart
  const chart = response.structured?.chart ?? response.chart ?? [];

  return (
    <div className="space-y-4">
      {/* Answer — bullets replace paragraph, rendered as markdown */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <span className="text-[11px] font-medium text-ink-muted uppercase tracking-[0.1em]">Result — bullets</span>
          <div className="flex-1 divider" />
        </div>
        <div className="text-[13px] leading-relaxed text-ink font-sans prose prose-invert max-w-none prose-p:my-1 prose-li:my-0.5 prose-ul:ml-4">
          <ReactMarkdown>{response.answer}</ReactMarkdown>
        </div>
        <span className="text-[10px] text-ink-muted">{response.answer.split(/\s+/).length} words · {response.answer.length} chars</span>
      </div>

      {/* Chart — bar/pie toggle, identical to Gradio */}
      {chart.length > 0 && <ChartPanel chart={chart} />}

      {/* Evidence */}
      {response.evidence.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-[11px] font-medium text-ink-muted uppercase tracking-[0.1em]">
              Evidence
            </span>
            <div className="flex-1 divider" />
            <span className="text-[11px] text-ink-muted">
              {response.evidence.length} item{response.evidence.length !== 1 ? "s" : ""}
            </span>
          </div>
          <div className="grid gap-2">
            {response.evidence.map((ev, i) => (
              <EvidenceBadge key={i} evidence={ev} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
