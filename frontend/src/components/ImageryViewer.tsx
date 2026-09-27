import type { ReactNode } from "react";
import type { UploadedImage, EvidenceRef, InputMode } from "../types/api";
import AmbientField from "./ui/AmbientField";
import { describeImage, sceneIdentity } from "../lib/imageMeta";

interface Props {
  images: UploadedImage[];
  inputMode: InputMode;
  evidence: EvidenceRef[];
  /** Real pending state of the outgoing request — drives the SCANNING step. */
  isRunning?: boolean;
  /** Whether a response has landed — drives the ANALYSIS READY step. */
  hasResponse?: boolean;
  /** Floating content rendered on top of the viewport (e.g. the result overlay). */
  overlay?: ReactNode;
}

/** Four corner brackets framing the imagery viewport. */
function ViewportCorners() {
  return (
    <div className="viewport-corners pointer-events-none absolute inset-0" aria-hidden="true">
      <div className="absolute left-3 top-3 h-4 w-4 border-l border-t border-teal-500/40" />
      <div className="absolute right-3 top-3 h-4 w-4 border-r border-t border-teal-500/40" />
      <div className="absolute bottom-3 left-3 h-4 w-4 border-b border-l border-teal-500/40" />
      <div className="absolute bottom-3 right-3 h-4 w-4 border-b border-r border-teal-500/40" />
    </div>
  );
}

function EvidenceCount({ count }: { count: number }) {
  return (
    <div className="pointer-events-none flex items-center gap-1.5 rounded-md border border-amber-500/20 bg-slate-950/80 px-1.5 py-0.5">
      <span className="h-1.5 w-1.5 rounded-full bg-amber-400" aria-hidden="true" />
      <span className="text-[10px] font-medium text-amber-300">
        {count} EVIDENCE
      </span>
    </div>
  );
}

/* ── Scan sequence ────────────────────────────────────────────────────────── */

type ScanStepId = "loaded" | "scanning" | "region" | "ready";

const SCAN_STEPS: { id: ScanStepId; label: string }[] = [
  { id: "loaded", label: "Image loaded" },
  { id: "scanning", label: "Scanning" },
  { id: "region", label: "Region detected" },
  { id: "ready", label: "Analysis ready" },
];

/**
 * The requested IMAGE LOADED → SCANNING → REGION DETECTED → ANALYSIS READY
 * sequence, gated on real application state.
 *
 * Each step lights only when the fact it names is true: imagery present, a
 * request genuinely in flight, evidence references actually returned, a
 * response actually landed. A response that carries no evidence leaves
 * REGION DETECTED unlit rather than faking a detection.
 */
function ScanSequence({
  hasImage,
  isRunning,
  hasEvidence,
  hasResponse,
}: {
  hasImage: boolean;
  isRunning: boolean;
  hasEvidence: boolean;
  hasResponse: boolean;
}) {
  const reached: Record<ScanStepId, boolean> = {
    loaded: hasImage,
    scanning: isRunning,
    region: hasEvidence,
    ready: hasResponse,
  };
  // A later step is only ever shown as reached if an earlier one is too.
  const order: ScanStepId[] = ["loaded", "scanning", "region", "ready"];
  const firstUnreached = order.findIndex((id) => !reached[id]);
  const liveIndex = isRunning ? 1 : firstUnreached === -1 ? order.length : firstUnreached;

  return (
    <div className="pointer-events-none flex flex-wrap items-center gap-x-2 gap-y-1">
      {SCAN_STEPS.map((step, i) => {
        const done = reached[step.id];
        const isLive = i === liveIndex;
        return (
          <span key={step.id} className="flex items-center gap-2">
            {i > 0 && (
              <span
                className={`h-px w-3 ${done || isLive ? "bg-teal-500/40" : "bg-slate-800"}`}
                aria-hidden="true"
              />
            )}
            <span
              className={`flex items-center gap-1.5 text-[9px] font-semibold uppercase tracking-[0.14em] transition-colors duration-300 ${
                done
                  ? "text-teal-300"
                  : isLive
                    ? "text-slate-400"
                    : "text-slate-600"
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full transition-colors duration-300 ${
                  done
                    ? "bg-teal-400"
                    : isLive
                      ? "animate-pulse bg-slate-500"
                      : "bg-slate-700"
                }`}
                aria-hidden="true"
              />
              {step.label}
            </span>
          </span>
        );
      })}
    </div>
  );
}

/* ── Metadata HUD ─────────────────────────────────────────────────────────── */

/**
 * Real metadata only. Rows come from `describeImage`, which reads the STAC
 * provenance the backend returned or the browser's own facts about the File.
 * Nothing is filled with a placeholder — an unknown field is simply absent.
 */
function ImageHud({ image, compact = false }: { image: UploadedImage; compact?: boolean }) {
  const rows = describeImage(image);
  if (rows.length === 0) return null;

  return (
    <dl
      className={`pointer-events-none space-y-0.5 ${
        compact ? "absolute left-2 top-8 max-w-[80%]" : "absolute left-4 top-4 max-w-[62%]"
      }`}
    >
      {rows.map((row) => (
        <div key={row.label} className="flex items-baseline gap-2 text-[10px]">
          <dt className="shrink-0 font-mono uppercase tracking-[0.1em] text-slate-600">
            {row.label}
          </dt>
          <dd
            className={`truncate text-slate-300 ${row.wide ? "max-w-[220px] font-mono text-[9px]" : ""}`}
            title={row.value}
          >
            {row.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/* ── Viewer ───────────────────────────────────────────────────────────────── */

export default function ImageryViewer({
  images,
  inputMode,
  evidence,
  isRunning = false,
  hasResponse = false,
  overlay,
}: Props) {
  const safeImages = Array.isArray(images) ? images.filter(Boolean) : [];
  const safeEvidence = Array.isArray(evidence) ? evidence : [];
  const primaryImage = safeImages[0];
  const hasImage = safeImages.length > 0;
  const hasEvidence = safeEvidence.length > 0;
  const bboxEvidence = safeEvidence.filter((e) => e.type === "bounding_box" && e.coordinates);
  const isBiTemporal = inputMode === "bi-temporal";

  return (
    <section className="panel flex-1">
      <header className="panel-header">
        <h2 className="panel-label">Satellite Imagery</h2>
        <span className="ml-auto flex items-center gap-3">
          <ScanSequence
            hasImage={hasImage}
            isRunning={isRunning}
            hasEvidence={hasEvidence}
            hasResponse={hasResponse}
          />
          <span className="tag-muted">{inputMode.replace("-", " + ").toUpperCase()}</span>
        </span>
      </header>

      <div className="relative min-h-0 flex-1 overflow-hidden bg-slate-950">
        <AmbientField />

        {isBiTemporal && hasImage ? (
          /* Bi-temporal: side-by-side T1 + T2 so both evidence image_index 0/1 are visible */
          <div className="absolute inset-0 flex">
            {[0, 1].map((idx) => {
              const img = safeImages[idx];
              const label = idx === 0 ? "T1 (BEFORE)" : "T2 (AFTER)";
              return (
                <div
                  key={idx}
                  className="relative flex-1 overflow-hidden border-r border-slate-800 last:border-r-0"
                >
                  {img ? (
                    <>
                      <img
                        src={img.preview}
                        alt={img.label}
                        className="absolute inset-0 h-full w-full bg-slate-950 object-contain"
                      />
                      <div className="absolute left-2 top-2 rounded bg-slate-950/80 px-1.5 py-0.5 text-[9px] font-bold tracking-widest text-slate-200">
                        {label}
                      </div>
                      <ImageHud image={img} compact />
                      <div
                        className="absolute bottom-2 left-2 max-w-[70%] truncate text-[10px] text-slate-500"
                        title={sceneIdentity(img)}
                      >
                        {sceneIdentity(img)}
                      </div>
                    </>
                  ) : (
                    <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-slate-600">
                      <span className="text-[11px]">Awaiting {label}</span>
                      <span className="text-[10px] opacity-70">
                        Upload {idx === 0 ? "Date 1" : "Date 2"} in input panel
                      </span>
                    </div>
                  )}
                </div>
              );
            })}
            <ViewportCorners />
            {isRunning && <ScanSweep />}
            {hasEvidence && (
              <div className="absolute bottom-4 right-4">
                <EvidenceCount count={safeEvidence.length} />
              </div>
            )}
          </div>
        ) : primaryImage ? (
          <>
            {/* Single / optical-sar single-pane */}
            <img
              src={primaryImage.preview}
              alt={primaryImage.label}
              className="absolute inset-0 h-full w-full object-contain"
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
                  className="evidence-box absolute border border-amber-400/80"
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
                  <div className="absolute -top-6 left-0 whitespace-nowrap rounded bg-slate-950/90 px-1.5 py-0.5 text-[9px] font-medium text-amber-300">
                    {ev.description}
                  </div>
                </div>
              );
            })}

            <ViewportCorners />
            <ImageHud image={primaryImage} />

            <div className="pointer-events-none absolute bottom-3 left-4 text-[11px] font-medium text-teal-300/80">
              {primaryImage.label.toUpperCase()}
            </div>

            <ScanSweep active={isRunning} />

            {hasEvidence && (
              <div className="absolute bottom-4 right-4">
                <EvidenceCount count={safeEvidence.length} />
              </div>
            )}
          </>
        ) : (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-5 px-8 text-center">
            <svg width="112" height="112" viewBox="0 0 96 96" fill="none" aria-hidden="true" className="text-slate-700">
              <circle cx="48" cy="48" r="40" stroke="currentColor" strokeWidth="0.75" strokeDasharray="3 3" />
              <circle cx="48" cy="48" r="20" stroke="currentColor" strokeWidth="0.75" />
              <circle cx="48" cy="48" r="2.5" fill="currentColor" />
              <line x1="48" y1="3" x2="48" y2="14" stroke="currentColor" strokeWidth="0.6" />
              <line x1="48" y1="82" x2="48" y2="93" stroke="currentColor" strokeWidth="0.6" />
              <line x1="3" y1="48" x2="14" y2="48" stroke="currentColor" strokeWidth="0.6" />
              <line x1="82" y1="48" x2="93" y2="48" stroke="currentColor" strokeWidth="0.6" />
            </svg>
            <div>
              <p className="text-[16px] font-medium tracking-wide text-slate-200">Satellite Imagery</p>
              <p className="mt-1.5 text-[13px] text-slate-500">Awaiting image input</p>
              <p className="mx-auto mt-3 max-w-sm text-[12px] leading-relaxed text-slate-600">
                Upload imagery from the input panel to begin analysis.
              </p>
            </div>
          </div>
        )}

        {overlay}
      </div>

      {/* Bottom info strip — file identity only, no invented metadata */}
      <div className="flex h-7 flex-shrink-0 items-center gap-5 border-t border-slate-800 bg-slate-900 px-4 text-[10px] text-slate-500">
        <span>
          {safeImages.length} image{safeImages.length === 1 ? "" : "s"}
        </span>
        {hasImage && <span className="truncate">{describeSceneSummary(safeImages, isBiTemporal)}</span>}
        <div className="flex-1" />
        {primaryImage?.meta?.collection && (
          <span className="font-mono text-slate-600">{primaryImage.meta.collection}</span>
        )}
        <span>{hasResponse ? "Response received" : hasImage ? "Ready to analyze" : "Awaiting data"}</span>
      </div>
    </section>
  );
}

/** Filename summary for the strip, using only real scene identities. */
function describeSceneSummary(images: UploadedImage[], isBiTemporal: boolean): string {
  const names = images.map(sceneIdentity);
  if (isBiTemporal && names.length > 1) return `${names[0]} → ${names[1]}`;
  return names[0] ?? "";
}

/**
 * Slow scanning line. Rendered only while a request is genuinely in flight, so
 * the motion always corresponds to real work. Collapses to nothing under
 * `prefers-reduced-motion`.
 */
function ScanSweep({ active = true }: { active?: boolean }) {
  if (!active) return null;
  return (
    <div className="scan-sweep pointer-events-none absolute inset-0" aria-hidden="true">
      <div className="scan-sweep-line absolute inset-x-0 top-0">
        <span className="block h-px w-full bg-gradient-to-r from-transparent via-teal-300/70 to-transparent" />
        <span className="block h-16 w-full bg-gradient-to-b from-teal-400/12 to-transparent" />
      </div>
    </div>
  );
}
