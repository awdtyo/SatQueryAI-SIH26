import type { QueryResponse, EvidenceRef } from "../types/api";

interface Props {
  response: QueryResponse | null;
}

function EvidenceBadge({ evidence }: { evidence: EvidenceRef }) {
  const icons: Record<EvidenceRef["type"], string> = {
    bounding_box: "\u25A2",
    overlay: "\u25C8",
    heatmap: "\u25A3",
    saliency: "\u25CE",
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

  return (
    <div className="space-y-4">
      {/* Answer — the most readable text on the page */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <span className="text-[11px] font-medium text-ink-muted uppercase tracking-[0.1em]">Result</span>
          <div className="flex-1 divider" />
        </div>
        <p className="text-[15px] leading-relaxed text-ink font-sans">
          {response.answer}
        </p>
      </div>

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
