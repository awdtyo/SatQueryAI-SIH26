import type { EvidenceRef, InputMode, UploadedImage } from "../types/api";
import { formatFileSize } from "../utils/format";

interface Props {
  images: UploadedImage[];
  inputMode: InputMode;
  evidence: EvidenceRef[];
}

export default function ImageryViewer({ images, inputMode, evidence }: Props) {
  const primaryImage = images[0];
  const hasEvidence = evidence.length > 0;
  const bboxEvidence = evidence.filter((e) => e.type === "bounding_box" && e.coordinates);

  return (
    <div className="relative flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-slate-800 bg-slate-950">
      <div className="panel-header flex-shrink-0 rounded-none border-b border-slate-800">
        <span className="panel-label">Satellite Imagery</span>
        <div className="flex-1" />
        <span className="tag-muted">{inputMode.replace("-", " + ").toUpperCase()}</span>
      </div>

      <div className="relative min-h-0 flex-1 overflow-hidden">
        {/* Subtle grid background */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            backgroundImage:
              "linear-gradient(rgba(45,212,191,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(45,212,191,0.04) 1px, transparent 1px)",
            backgroundSize: "28px 28px",
          }}
        />

        {primaryImage ? (
          <>
            <img
              src={primaryImage.preview}
              alt={primaryImage.label}
              className="absolute inset-0 h-full w-full object-contain"
            />

            {bboxEvidence.map((ev, i) => {
              if (!ev.coordinates || ev.coordinates.length < 4) return null;
              const pts = ev.coordinates;
              const xs = pts.map((p) => p[0]!);
              const ys = pts.map((p) => p[1]!);
              const minX = Math.min(...xs);
              const minY = Math.min(...ys);
              const maxX = Math.max(...xs);
              const maxY = Math.max(...ys);
              return (
                <div
                  key={i}
                  className="absolute border border-amber-400/80"
                  style={{
                    left: `${(minX / 400) * 100}%`,
                    top: `${(minY / 300) * 100}%`,
                    width: `${((maxX - minX) / 400) * 100}%`,
                    height: `${((maxY - minY) / 300) * 100}%`,
                  }}
                >
                  <div className="absolute -left-px -top-px h-2 w-2 border-l-2 border-t-2 border-amber-400" />
                  <div className="absolute -right-px -top-px h-2 w-2 border-r-2 border-t-2 border-amber-400" />
                  <div className="absolute -bottom-px -left-px h-2 w-2 border-b-2 border-l-2 border-amber-400" />
                  <div className="absolute -bottom-px -right-px h-2 w-2 border-b-2 border-r-2 border-amber-400" />
                  <div className="absolute -top-6 left-0 whitespace-nowrap rounded bg-slate-950/90 px-1.5 py-0.5 text-[9px] font-medium text-amber-400">
                    {ev.description}
                  </div>
                </div>
              );
            })}

            <div className="absolute left-3 top-3 h-4 w-4 border-l border-t border-teal-500/30 pointer-events-none" />
            <div className="absolute right-3 top-3 h-4 w-4 border-r border-t border-teal-500/30 pointer-events-none" />
            <div className="absolute bottom-3 left-3 h-4 w-4 border-b border-l border-teal-500/30 pointer-events-none" />
            <div className="absolute bottom-3 right-3 h-4 w-4 border-b border-r border-teal-500/30 pointer-events-none" />

            <div className="absolute left-4 top-3 space-y-0.5 text-[10px] text-slate-500/80 pointer-events-none">
              <div className="font-mono">ANALYSIS VIEW</div>
              <div>{primaryImage.file.type || "UNKNOWN"} · {formatFileSize(primaryImage.file.size)}</div>
            </div>

            <div className="absolute bottom-3 left-4 text-[11px] font-medium text-teal-400/80 pointer-events-none">
              {primaryImage.label.toUpperCase()}
            </div>

            {hasEvidence && (
              <div className="absolute bottom-3 right-4 flex items-center gap-1.5 pointer-events-none">
                <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
                <span className="text-[10px] font-medium text-amber-400/80">{evidence.length} EVIDENCE</span>
              </div>
            )}
          </>
        ) : (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-5 px-8 text-center">
            <div className="relative h-28 w-28">
              <svg width="112" height="112" viewBox="0 0 96 96" fill="none" className="text-teal-500/25">
                <circle cx="48" cy="48" r="40" stroke="currentColor" strokeWidth="0.75" strokeDasharray="3 3" />
                <circle cx="48" cy="48" r="20" stroke="currentColor" strokeWidth="0.75" />
                <circle cx="48" cy="48" r="2.5" fill="currentColor" />
                <line x1="48" y1="3" x2="48" y2="14" stroke="currentColor" strokeWidth="0.6" />
                <line x1="48" y1="82" x2="48" y2="93" stroke="currentColor" strokeWidth="0.6" />
                <line x1="3" y1="48" x2="14" y2="48" stroke="currentColor" strokeWidth="0.6" />
                <line x1="82" y1="48" x2="93" y2="48" stroke="currentColor" strokeWidth="0.6" />
              </svg>
            </div>
            <div>
              <p className="text-[16px] font-medium tracking-wide text-slate-200">Satellite Imagery</p>
              <p className="mt-1.5 text-[13px] text-slate-400">Awaiting image input</p>
              <p className="mt-3 max-w-sm text-[12px] leading-relaxed text-slate-500">
                Upload imagery from the input panel to begin analysis.
              </p>
            </div>
          </div>
        )}
      </div>

      <div className="flex h-7 flex-shrink-0 items-center gap-5 border-t border-slate-800 bg-slate-900 px-4 text-[10px] text-slate-500">
        <span>
          Bands:{" "}
          {inputMode === "optical-sar" ? "OPT + SAR" : inputMode === "bi-temporal" ? "T1 + T2" : "RGB"}
        </span>
        <span>Res: Auto</span>
        <div className="flex-1" />
        {primaryImage ? (
          <span className="truncate max-w-[40%]">{primaryImage.file.name}</span>
        ) : (
          <span>Awaiting data</span>
        )}
      </div>
    </div>
  );
}