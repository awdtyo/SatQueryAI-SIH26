import type { SatelliteScene } from "../types/satellite";

interface Props {
  scene: SatelliteScene | null;
  onClear: () => void;
  onActivate: (scene: SatelliteScene) => void;
}

/**
 * Selected Satellite Image Query Mode — prominent Active Scene card shown above the
 * query input. Tells the user exactly which live scene their next NL query will be
 * analyzed against, with [Query This Image] and [Change Scene].
 */
export default function ActiveSceneContext({ scene, onClear, onActivate }: Props) {
  if (!scene) {
    return (
      <div className="flex items-center gap-2 text-[11px] text-ink-muted">
        <span className="w-1.5 h-1.5 rounded-full bg-ink-muted" />
        <span>
          No active satellite image — run a <span className="text-accent">Live Satellite Search</span>, pick a
          scene, then <span className="text-ink-secondary">Query This Image</span> to analyze its real band assets.
        </span>
      </div>
    );
  }

  const label = scene.platform ? `${scene.platform}` : scene.collection;
  const date = scene.datetime ? new Date(scene.datetime).toLocaleDateString() : "—";

  return (
    <div className="flex items-center gap-3 flex-wrap px-3 py-2 rounded-lg border border-accent/30 bg-accent/5">
      <span className="text-[12px]" title="Active satellite image">🛰️</span>
      <div className="min-w-0">
        <div className="flex items-center gap-2 text-[11px] font-semibold text-ink">
          <span className="text-accent">Active Satellite Image</span>
          <span className="tag-muted truncate max-w-[220px] font-mono">{scene.id}</span>
          <span className="text-ink-muted font-normal truncate">
            {label} · {date} · cloud {scene.cloud_cover != null ? `${scene.cloud_cover.toFixed(1)}%` : "—"}
          </span>
        </div>
        <div className="text-[10px] text-ink-muted truncate">
          Your next question analyzes the selected scene's real Sentinel-2 assets{scene.bbox ? " (AOI-clipped)" : ""}.
        </div>
      </div>
      <div className="ml-auto flex items-center gap-2 flex-shrink-0">
        <button
          onClick={() => onActivate(scene)}
          className="px-3 py-1.5 rounded bg-accent text-surface-950 text-[11px] font-semibold hover:bg-accent-bright transition-colors"
          title="Re-affirm this scene as the active analysis context"
        >
          Query This Image →
        </button>
        <button
          onClick={onClear}
          className="px-3 py-1.5 rounded border border-surface-400/30 text-[11px] text-ink-muted hover:text-signal-red transition-colors"
          title="Deactivate this scene — you will be asked to pick another scene"
        >
          Change Scene
        </button>
      </div>
    </div>
  );
}