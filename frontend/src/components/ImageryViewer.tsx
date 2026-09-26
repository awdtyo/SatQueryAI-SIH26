import type { EvidenceRef, InputMode, UploadedImage } from "../types/api";
import { formatFileSize } from "../lib/format";
import { CrosshairIcon, SatelliteIcon } from "./ui/Icons";
import { usePrefersReducedMotion } from "../hooks/usePrefersReducedMotion";

interface Props {
  images: UploadedImage[];
  inputMode: InputMode;
  evidence: EvidenceRef[];
  /** True while a request is in flight — drives the acquisition scan. */
  analyzing?: boolean;
}

/** Pixel-space of the evidence boxes, matching the backend YOLO canvas. */
const EVIDENCE_CANVAS = { width: 400, height: 300 } as const;

function modeLabel(mode: InputMode): string {
  if (mode === "optical-sar") return "OPTICAL + SAR";
  if (mode === "bi-temporal") return "BI-TEMPORAL";
  return "SINGLE";
}

function bandLabel(mode: InputMode): string {
  if (mode === "optical-sar") return "OPT + SAR";
  if (mode === "bi-temporal") return "T1 + T2";
  return "RGB";
}

function EvidenceBadge({ count }: { count: number }) {
  return (
    <div className="pointer-events-none flex items-center gap-1.5 rounded-md border border-amber-500/20 bg-slate-950/80 px-2 py-1 backdrop-blur-sm">
      <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
      <span className="text-[10px] font-medium text-amber-300">
        {count} EVIDENCE
      </span>
    </div>
  );
}

function CornerBrackets() {
  return (
    <>
      <div className="pointer-events-none absolute left-3 top-3 h-4 w-4 border-l border-t border-teal-500/40" />
      <div className="pointer-events-none absolute right-3 top-3 h-4 w-4 border-r border-t border-teal-500/40" />
      <div className="pointer-events-none absolute bottom-3 left-3 h-4 w-4 border-b border-l border-teal-500/40" />
      <div className="pointer-events-none absolute bottom-3 right-3 h-4 w-4 border-b border-r border-teal-500/40" />
    </>
  );
}

/** Section 4 — a coordinate grid that reads as targeting reticules, not a texture. */
function TargetingGrid() {
  return (
    <div className="imagery-grid pointer-events-none absolute inset-0" aria-hidden="true">
      <div className="absolute left-1/4 top-0 h-full w-px bg-teal-500/[0.07]" />
      <div className="absolute left-1/2 top-0 h-full w-px bg-teal-500/[0.07]" />
      <div className="absolute left-3/4 top-0 h-full w-px bg-teal-500/[0.07]" />
      <div className="absolute left-0 top-1/4 h-px w-full bg-teal-500/[0.07]" />
      <div className="absolute left-0 top-1/2 h-px w-full bg-teal-500/[0.07]" />
      <div className="absolute left-0 top-3/4 h-px w-full bg-teal-500/[0.07]" />
    </div>
  );
}

/**
 * The acquisition scan. Always mounted, and its opacity is driven by `active`
 * through a transition, so when the request resolves the scan dissolves out of
 * the viewport rather than being yanked from it.
 */
function ScanOverlay({ active, reduced }: { active: boolean; reduced: boolean }) {
  return (
    <div className="imagery-scan-layer" data-active={active && !reduced}>
      <div className="imagery-scan absolute inset-0" aria-hidden="true" />
      <div className="imagery-scanline absolute inset-x-0 top-0 h-24" aria-hidden="true" />
    </div>
  );
}

function EvidenceBoxes({ evidence }: { evidence: EvidenceRef[] }) {
  return (
    <>
      {evidence.map((ev, i) => {
        if (!ev.coordinates || ev.coordinates.length < 4) return null;
        const xs = ev.coordinates.map((p) => p[0]!);
        const ys = ev.coordinates.map((p) => p[1]!);
        const minX = Math.min(...xs);
        const minY = Math.min(...ys);
        const maxX = Math.max(...xs);
        const maxY = Math.max(...ys);
        return (
          <div
            key={i}
            className="evidence-roi absolute border border-amber-400/80"
            data-entering="false"
            style={{
              left: `${(minX / EVIDENCE_CANVAS.width) * 100}%`,
              top: `${(minY / EVIDENCE_CANVAS.height) * 100}%`,
              width: `${((maxX - minX) / EVIDENCE_CANVAS.width) * 100}%`,
              height: `${((maxY - minY) / EVIDENCE_CANVAS.height) * 100}%`,
            }}
          >
            <div className="absolute -left-px -top-px h-2 w-2 border-l-2 border-t-2 border-amber-400" />
            <div className="absolute -right-px -top-px h-2 w-2 border-r-2 border-t-2 border-amber-400" />
            <div className="absolute -bottom-px -left-px h-2 w-2 border-b-2 border-l-2 border-amber-400" />
            <div className="absolute -bottom-px -right-px h-2 w-2 border-b-2 border-r-2 border-amber-400" />
            <div className="absolute -top-6 left-0 max-w-[16rem] truncate whitespace-nowrap rounded border border-amber-500/20 bg-slate-950/90 px-1.5 py-0.5 text-[9px] font-medium text-amber-300 backdrop-blur-sm">
              {ev.description}
            </div>
          </div>
        );
      })}
    </>
  );
}

function EmptyViewport() {
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center gap-5 px-8 text-center">
      <SatelliteIcon className="h-24 w-24 text-teal-500/20" strokeWidth={0.6} />
      <div>
        <p className="text-[16px] font-medium tracking-wide text-slate-200">Satellite Imagery</p>
        <p className="mt-1.5 text-[13px] text-slate-500">Awaiting image input</p>
        <p className="mx-auto mt-3 max-w-sm text-[12px] leading-relaxed text-slate-400">
          Upload imagery from the input panel to begin analysis.
        </p>
      </div>
    </div>
  );
}

export default function ImageryViewer({ images, inputMode, evidence, analyzing = false }: Props) {
  const reduced = usePrefersReducedMotion();
  const primaryImage = images[0];
  const isBiTemporal = inputMode === "bi-temporal";
  const hasEvidence = evidence.length > 0;
  const bboxEvidence = evidence.filter((e) => e.type === "bounding_box" && e.coordinates);
  // The scan runs while the request is open and yields the moment evidence lands.
  const scanning = analyzing && !hasEvidence;

  return (
    <section className="panel flex min-h-0 flex-1 flex-col overflow-hidden">
      <header className="panel-header">
        <h2 className="panel-label">Satellite Imagery</h2>
        <div className="flex-1" />
        {scanning && (
          <span className="chip-accent">
            <span className="h-1.5 w-1.5 animate-status-pulse rounded-full bg-current" />
            Scanning
          </span>
        )}
        <span className="chip-muted">{modeLabel(inputMode)}</span>
      </header>

      <div className="map-grid relative flex-1 overflow-hidden bg-slate-950">
        {isBiTemporal && images.length > 0 ? (
          <div className="absolute inset-0 flex">
            {[0, 1].map((idx) => {
              const img = images[idx];
              const label = idx === 0 ? "T1 (BEFORE)" : "T2 (AFTER)";
              return (
                <div
                  key={idx}
                  className="relative flex-1 overflow-hidden border-r border-slate-800/60 last:border-r-0"
                >
                  {img ? (
                    <>
                      <img
                        src={img.preview}
                        alt={img.label}
                        className="absolute inset-0 h-full w-full bg-slate-950 object-contain"
                      />
                      <div className="absolute left-2 top-2 rounded border border-slate-700/70 bg-slate-950/80 px-1.5 py-0.5 text-[9px] font-bold tracking-widest text-slate-200 backdrop-blur-sm">
                        {label}
                      </div>
                      <div className="absolute bottom-2 left-2 max-w-[70%] truncate text-[10px] text-slate-500">
                        {img.file.name}
                      </div>
                    </>
                  ) : (
                    <div className="absolute inset-0 flex flex-col items-center justify-center gap-1.5 text-slate-500">
                      <span className="text-[11px]">Awaiting {label}</span>
                      <span className="text-[10px] opacity-70">
                        Upload {idx === 0 ? "Date 1" : "Date 2"} in the input panel
                      </span>
                    </div>
                  )}
                </div>
              );
            })}
            <CornerBrackets />
            {hasEvidence && (
              <div className="absolute bottom-4 right-4">
                <EvidenceBadge count={evidence.length} />
              </div>
            )}
          </div>
        ) : primaryImage ? (
          <>
            <img
              src={primaryImage.preview}
              alt={primaryImage.label}
              className="absolute inset-0 h-full w-full object-contain"
            />
            <EvidenceBoxes evidence={bboxEvidence} />
            <TargetingGrid />
            <ScanOverlay active={scanning} reduced={reduced} />
            <CornerBrackets />

            <div className="pointer-events-none absolute left-4 top-4 flex items-center gap-2">
              <CrosshairIcon className="h-3.5 w-3.5 text-teal-400/70" />
              <div className="space-y-0.5 rounded-md border border-slate-800/60 bg-slate-950/70 px-2.5 py-1.5 backdrop-blur-sm">
                <div className="font-mono text-[10px] uppercase tracking-widest text-slate-500">
                  Analysis view
                </div>
                <div className="text-[10px] text-slate-500">
                  {primaryImage.file.type || "UNKNOWN"} · {formatFileSize(primaryImage.file.size)}
                </div>
              </div>
            </div>

            <div className="pointer-events-none absolute bottom-4 left-4 rounded-md border border-slate-800/60 bg-slate-950/70 px-2.5 py-1 text-[11px] font-medium uppercase tracking-wider text-teal-300 backdrop-blur-sm">
              {primaryImage.label}
            </div>

            {hasEvidence && (
              <div className="absolute bottom-4 right-4">
                <EvidenceBadge count={evidence.length} />
              </div>
            )}
          </>
        ) : (
          <EmptyViewport />
        )}
      </div>

      <footer className="flex h-8 flex-shrink-0 items-center gap-5 border-t border-slate-800/80 bg-slate-900 px-4 text-[10px] text-slate-500">
        <span>Bands: {bandLabel(inputMode)}</span>
        <span>Res: Auto</span>
        {scanning && <span className="text-teal-400/80">Acquiring…</span>}
        <div className="flex-1" />
        {images.length > 0 ? (
          <span className="max-w-[45%] truncate">
            {isBiTemporal
              ? `${images[0]?.file.name ?? "?"} → ${images[1]?.file.name ?? "?"}`
              : primaryImage!.file.name}
          </span>
        ) : (
          <span>Awaiting data</span>
        )}
      </footer>
    </section>
  );
}
