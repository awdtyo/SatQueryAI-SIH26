import type { SatelliteScene } from "../types/satellite";

interface Props {
  scene: SatelliteScene | null;
  onSelectForAnalysis?: (scene: SatelliteScene) => void;
}

export default function SceneMetadataPanel({ scene, onSelectForAnalysis }: Props) {
  if (!scene) {
    return (
      <div className="panel p-4 text-center">
        <div className="text-[11px] text-ink-muted">Select a satellite scene to inspect its metadata.</div>
        <div className="text-[10px] text-ink-muted mt-1">Click a footprint on the map or a card below.</div>
      </div>
    );
  }

  const assetsEntries = Object.entries(scene.assets || {}).slice(0, 12);

  return (
    <div className="panel overflow-hidden">
      <div className="panel-header">
        <span className="panel-label">Selected Scene</span>
        <span className="ml-auto tag-muted truncate max-w-[140px] text-[10px]">{scene.id.slice(0, 24)}</span>
      </div>
      <div className="panel-body space-y-3">
        {scene.thumbnail ? (
          <img src={scene.thumbnail} alt={scene.id} className="w-full h-40 object-cover rounded border border-surface-400/30 bg-surface-900" onError={(e) => ((e.target as HTMLImageElement).style.display = "none")} />
        ) : (
          <div className="w-full h-24 rounded bg-surface-800 border border-dashed border-surface-400/30 flex items-center justify-center text-[11px] text-ink-muted">Preview unavailable</div>
        )}

        <div className="space-y-2 text-[11px]">
          <div className="flex justify-between">
            <span className="text-ink-muted">Scene ID</span>
            <span className="text-ink font-mono text-[11px] truncate max-w-[160px]" title={scene.id}>
              {scene.id}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-ink-muted">Acquired</span>
            <span className="text-ink">{scene.datetime ? new Date(scene.datetime).toLocaleString() : "—"}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-ink-muted">Platform</span>
            <span className="text-ink">{scene.platform || "—"} · {scene.collection}</span>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <div className="bg-surface-900 border border-surface-400/30 rounded p-2 text-center">
              <div className="text-[10px] text-ink-muted uppercase">Cloud</div>
              <div className="text-[12px] font-semibold text-ink">{scene.cloud_cover != null ? `${scene.cloud_cover.toFixed(1)}%` : "—"}</div>
            </div>
            <div className="bg-surface-900 border border-surface-400/30 rounded p-2 text-center">
              <div className="text-[10px] text-ink-muted uppercase">Coverage</div>
              <div className="text-[12px] font-semibold text-accent">{scene.coverage != null ? `${scene.coverage.toFixed(1)}%` : "—"}</div>
            </div>
            <div className="bg-surface-900 border border-surface-400/30 rounded p-2 text-center">
              <div className="text-[10px] text-ink-muted uppercase">Score</div>
              <div className="text-[12px] font-semibold text-signal-green">{scene.selection_score != null ? scene.selection_score.toFixed(3) : "—"}</div>
            </div>
          </div>
          <div>
            <div className="text-[11px] font-medium text-ink-muted mb-1">Assets ({Object.keys(scene.assets || {}).length})</div>
            <div className="flex flex-wrap gap-1">
              {assetsEntries.length > 0 ? (
                assetsEntries.map(([k, href]) => (
                  <a key={k} href={href} target="_blank" rel="noopener noreferrer" className="px-1.5 py-0.5 rounded bg-surface-800 border border-surface-400/30 text-[10px] font-mono text-accent hover:text-accent-bright hover:border-accent/50 transition-colors">
                    {k}
                  </a>
                ))
              ) : (
                <span className="text-[10px] text-ink-muted">No assets</span>
              )}
            </div>
            {Object.keys(scene.assets || {}).length > 12 && <div className="text-[10px] text-ink-muted mt-1">+{Object.keys(scene.assets).length - 12} more</div>}
          </div>
        </div>

        {onSelectForAnalysis && (
          <button onClick={() => onSelectForAnalysis(scene)} className="w-full py-2 rounded bg-accent text-surface-900 text-[12px] font-semibold hover:bg-accent-bright transition-colors">
            Select for Analysis →
          </button>
        )}
        <div className="text-[10px] text-ink-muted leading-relaxed">Selected scene stored in app state. Continue to existing VQA / change / counting with its band assets (future: `retrieve_scene_assets`).</div>
      </div>
    </div>
  );
}
