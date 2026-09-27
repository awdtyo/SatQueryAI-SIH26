import type { HealthState, InputMode, UploadedImage } from "../types/api";
import { computeLabel, deviceLabel } from "../lib/systemStatus";
import { formatBytes, formatCoords, isResolvedScene } from "../lib/imageMeta";

interface Props {
  images: UploadedImage[];
  inputMode: InputMode;
  inputSource: "upload" | "location";
  health: HealthState;
}

/**
 * Fills the left column with information the app actually has.
 *
 * Everything on this card is read from live state: the selected mode and
 * source, the STAC provenance the backend returned for any location-resolved
 * scene, and the model / compute values from the health probe. Rows with no
 * real value are omitted, so an idle panel reads as genuinely empty rather than
 * showing plausible filler.
 */
export default function ImagerySourceCard({ images, inputMode, inputSource, health }: Props) {
  const resolved = images.filter((i) => i.meta?.collection || i.meta?.scene_id);
  const primary = images[0];

  const rows: { label: string; value: string }[] = [];

  rows.push({ label: "Source", value: inputSource === "location" ? "Location lookup" : "Local upload" });
  rows.push({
    label: "Mode",
    value: inputMode === "optical-sar" ? "Optical + SAR" : inputMode === "bi-temporal" ? "Bi-temporal" : "Single scene",
  });

  const collection = resolved[0]?.meta?.collection;
  if (collection) rows.push({ label: "Collection", value: collection });

  const sceneId = resolved[0]?.meta?.scene_id;
  if (sceneId) rows.push({ label: "Scene", value: sceneId });

  const coords = formatCoords(primary?.meta?.lat, primary?.meta?.lon);
  if (coords) rows.push({ label: "Centre", value: coords });

  // A resolved scene's byte count is the size of the base64 preview wrapper the
  // app built, not the source raster — label it honestly, and drop it when the
  // decode failed and there is nothing real to report.
  if (primary) {
    const resolvedScene = isResolvedScene(primary);
    if (resolvedScene) {
      if (primary.file.size > 0) {
        rows.push({ label: "Preview", value: formatBytes(primary.file.size) });
      }
    } else {
      rows.push({ label: "Payload", value: formatBytes(primary.file.size) });
    }
  }

  const baseModel = health?.base_model?.trim();
  if (baseModel) rows.push({ label: "Model", value: baseModel });

  const compute = computeLabel(health);
  if (compute) rows.push({ label: "Compute", value: compute });

  const device = deviceLabel(health);
  if (device) rows.push({ label: "Device", value: device });

  return (
    <section className="panel flex-shrink-0">
      <header className="panel-header">
        <h2 className="panel-label">Data Source</h2>
        <span className="tag-muted ml-auto">
          {inputSource === "location" ? "LIVE" : "LOCAL"}
        </span>
      </header>

      <div className="panel-body">
        <dl className="space-y-1.5">
          {rows.map((row) => (
            <div key={row.label} className="flex items-baseline justify-between gap-3">
              <dt className="shrink-0 text-[10px] font-medium uppercase tracking-[0.1em] text-slate-600">
                {row.label}
              </dt>
              <span className="min-w-[8px] flex-1 border-b border-dotted border-slate-800" />
              <dd
                className="max-w-[55%] truncate text-right text-[11px] text-slate-400"
                title={row.value}
              >
                {row.value}
              </dd>
            </div>
          ))}
        </dl>

        {resolved.length > 0 && (
          <p className="mt-3 flex items-center gap-1.5 border-t border-slate-800 pt-3 text-[10px] leading-relaxed text-emerald-400">
            <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-emerald-400" aria-hidden="true" />
            {resolved.length} scene{resolved.length === 1 ? "" : "s"} resolved from the satellite
            archive.
          </p>
        )}

        {!primary && (
          <p className="mt-3 border-t border-slate-800 pt-3 text-[10px] leading-relaxed text-slate-600">
            No imagery yet. Upload a file or resolve a location — provenance appears here once
            the source is real.
          </p>
        )}
      </div>
    </section>
  );
}
