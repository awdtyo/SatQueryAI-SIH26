import type { UploadedImage, EvidenceRef, InputMode } from "../types/api";

interface Props {
  images: UploadedImage[];
  inputMode: InputMode;
  evidence: EvidenceRef[];
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ImageryViewer({ images, inputMode, evidence }: Props) {
  const primaryImage = images[0];
  const hasEvidence = evidence.length > 0;
  const bboxEvidence = evidence.filter((e) => e.type === "bounding_box" && e.coordinates);

  return (
    <div className="panel flex-1 flex flex-col min-h-0 relative">
      {/* Panel header */}
      <div className="panel-header flex-shrink-0">
        <span className="panel-label">Satellite Imagery</span>
        <div className="flex-1" />
        <span className="tag-muted">{inputMode.replace("-", " + ").toUpperCase()}</span>
      </div>

      {/* Viewer area */}
      <div className="flex-1 relative bg-surface-900 overflow-hidden">
        {/* Subtle grid background (reduced opacity) */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            backgroundImage:
              "linear-gradient(rgba(50,215,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(50,215,255,0.03) 1px, transparent 1px)",
            backgroundSize: "28px 28px",
          }}
        />

        {primaryImage ? (
          <>
            {/* Image */}
            <img
              src={primaryImage.preview}
              alt={primaryImage.label}
              className="absolute inset-0 w-full h-full object-contain"
            />

            {/* Evidence bounding boxes */}
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
                  className="absolute border border-signal-amber/80"
                  style={{
                    left: `${(minX / 400) * 100}%`,
                    top: `${(minY / 300) * 100}%`,
                    width: `${((maxX - minX) / 400) * 100}%`,
                    height: `${((maxY - minY) / 300) * 100}%`,
                  }}
                >
                  <div className="absolute -top-px -left-px w-2 h-2 border-t-2 border-l-2 border-signal-amber" />
                  <div className="absolute -top-px -right-px w-2 h-2 border-t-2 border-r-2 border-signal-amber" />
                  <div className="absolute -bottom-px -left-px w-2 h-2 border-b-2 border-l-2 border-signal-amber" />
                  <div className="absolute -bottom-px -right-px w-2 h-2 border-b-2 border-r-2 border-signal-amber" />
                  <div className="absolute -top-6 left-0 text-[9px] font-medium text-signal-amber bg-surface-900/90 px-1.5 py-0.5 whitespace-nowrap rounded">
                    {ev.description}
                  </div>
                </div>
              );
            })}

            {/* Corner brackets */}
            <div className="absolute top-3 left-3 w-4 h-4 border-t border-l border-accent/30 pointer-events-none" />
            <div className="absolute top-3 right-3 w-4 h-4 border-t border-r border-accent/30 pointer-events-none" />
            <div className="absolute bottom-3 left-3 w-4 h-4 border-b border-l border-accent/30 pointer-events-none" />
            <div className="absolute bottom-3 right-3 w-4 h-4 border-b border-r border-accent/30 pointer-events-none" />

            {/* Top-left info */}
            <div className="absolute top-3 left-4 text-[10px] text-ink-muted/70 pointer-events-none space-y-0.5">
              <div className="font-mono">ANALYSIS VIEW</div>
              <div>{primaryImage.file.type || "UNKNOWN"} · {formatFileSize(primaryImage.file.size)}</div>
            </div>

            {/* Bottom-left label */}
            <div className="absolute bottom-3 left-4 text-[11px] font-medium text-accent/70 pointer-events-none">
              {primaryImage.label.toUpperCase()}
            </div>

            {/* Bottom-right evidence count */}
            {hasEvidence && (
              <div className="absolute bottom-3 right-4 flex items-center gap-1.5 pointer-events-none">
                <span className="w-1.5 h-1.5 rounded-full bg-signal-amber" />
                <span className="text-[10px] font-medium text-signal-amber/80">{evidence.length} EVIDENCE</span>
              </div>
            )}
          </>
        ) : (
          /* Bright professional empty state */
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-5 px-8 text-center">
            <div className="relative w-28 h-28">
              <svg width="112" height="112" viewBox="0 0 96 96" fill="none" className="text-accent/25">
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
              <p className="text-[16px] font-medium text-ink tracking-wide">Satellite Imagery</p>
              <p className="text-[13px] text-ink-muted mt-1.5">
                Awaiting image input
              </p>
              <p className="text-[12px] text-ink-muted/70 mt-3 max-w-sm leading-relaxed">
                Upload imagery from the input panel to begin analysis.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Bottom info strip */}
      <div className="flex-shrink-0 h-7 flex items-center px-4 border-t border-surface-400/25 bg-surface-800 text-[10px] text-ink-muted/70 gap-5">
        <span>Bands: {inputMode === "optical-sar" ? "OPT + SAR" : inputMode === "bi-temporal" ? "T1 + T2" : "RGB"}</span>
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
