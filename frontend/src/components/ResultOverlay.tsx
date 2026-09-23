import type { EvidenceRef, QueryResponse } from "../types/api";
import LandCoverChart from "./LandCoverChart";
import ModelLatencyChart from "./ModelLatencyChart";
import { IconClose } from "./icons";

interface Props {
  response: QueryResponse;
  onClose: () => void;
}

function SectionHeader({ children }: { children: string }) {
  return (
    <h3 className="mb-2.5 flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.1em] text-slate-400">
      {children}
      <span className="flex-1 border-t border-slate-800" />
    </h3>
  );
}

function EvidenceBadge({ evidence }: { evidence: EvidenceRef }) {
  const icons: Record<EvidenceRef["type"], string> = {
    bounding_box: "\u25A2",
    overlay: "\u25C8",
    heatmap: "\u25A3",
    saliency: "\u25CE",
  };

  return (
    <div className="flex items-start gap-3 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2.5">
      <span className="mt-0.5 text-sm text-teal-400">{icons[evidence.type]}</span>
      <div className="min-w-0">
        <span className="block text-[11px] font-medium text-teal-400">
          {evidence.type.replace("_", " ").toUpperCase()}
        </span>
        <span className="text-[12px] leading-snug text-slate-300">{evidence.description}</span>
      </div>
    </div>
  );
}

export default function ResultOverlay({ response, onClose }: Props) {
  return (
    <aside
      aria-label="Intelligence result"
      className="absolute bottom-4 right-4 max-h-[calc(100%-2rem)] w-full max-w-md animate-slide-up overflow-y-auto rounded-xl border border-slate-800 bg-slate-900/80 shadow-2xl shadow-black/50 backdrop-blur-md"
    >
      <div className="sticky top-0 z-10 flex items-center gap-2.5 border-b border-slate-800 bg-slate-900/90 px-4 py-3 backdrop-blur-md">
        <span className="panel-label">Intelligence Result</span>
        <div className="flex-1" />
        <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-400">
          Received
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close result panel"
          className="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/60"
        >
          <IconClose />
        </button>
      </div>

      <div className="space-y-5 p-4">
        <section>
          <SectionHeader>Result</SectionHeader>
          <p className="text-[14px] leading-relaxed text-slate-200">{response.answer}</p>
        </section>

        {response.land_cover && response.land_cover.length > 0 && (
          <section>
            <SectionHeader>Land Cover Distribution</SectionHeader>
            <LandCoverChart slices={response.land_cover} />
          </section>
        )}

        {response.execution_trace.models_used.length > 0 && (
          <section>
            <SectionHeader>Model Latency</SectionHeader>
            <ModelLatencyChart models={response.execution_trace.models_used} />
          </section>
        )}

        {response.evidence.length > 0 && (
          <section>
            <SectionHeader>Evidence</SectionHeader>
            <div className="grid gap-2">
              {response.evidence.map((ev, i) => (
                <EvidenceBadge key={i} evidence={ev} />
              ))}
            </div>
          </section>
        )}
      </div>
    </aside>
  );
}