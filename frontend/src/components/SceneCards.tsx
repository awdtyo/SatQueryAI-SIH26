import type { SatelliteScene } from "../types/satellite";

interface Props {
  scenes: SatelliteScene[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export default function SceneCards({ scenes, selectedId, onSelect }: Props) {
  if (scenes.length === 0) return null;
  return (
    <div className="space-y-2">
      <div className="text-[11px] font-medium text-ink-muted uppercase tracking-wide">Results ({scenes.length}) — ranked by selection_score · Map ↔ cards synced</div>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2 max-h-[32vh] overflow-y-auto pr-1">
        {scenes.map((s) => (
          <button
            key={s.id}
            onClick={() => onSelect(s.id)}
            className={`text-left border rounded-lg overflow-hidden transition-all w-full ${
              selectedId === s.id ? "border-accent bg-accent/10 ring-1 ring-accent" : "border-surface-400/30 bg-surface-800/40 hover:border-surface-400/60"
            }`}
          >
            <div className="flex gap-2 p-2">
              {s.thumbnail ? (
                <img
                  src={s.thumbnail}
                  alt={s.id}
                  className="w-16 h-16 object-cover rounded bg-surface-900 flex-shrink-0"
                  onError={(e) => ((e.target as HTMLImageElement).style.display = "none")}
                />
              ) : (
                <div className="w-16 h-16 rounded bg-surface-900 flex items-center justify-center text-[10px] text-ink-muted flex-shrink-0">no preview</div>
              )}
              <div className="flex-1 min-w-0">
                <div className="text-[11px] font-mono text-ink truncate" title={s.id}>
                  {s.id}
                </div>
                <div className="text-[11px] text-ink-secondary truncate">{s.datetime ? new Date(s.datetime).toLocaleDateString() : "—"} · {s.platform || "sentinel-2"}</div>
                <div className="flex gap-1.5 mt-1 flex-wrap">
                  <span className="px-1 py-0.5 rounded bg-surface-900 border border-surface-400/30 text-[10px] text-ink-muted">cloud {s.cloud_cover != null ? `${s.cloud_cover.toFixed(1)}%` : "—"}</span>
                  <span className="px-1 py-0.5 rounded bg-surface-900 border border-surface-400/30 text-[10px] text-ink-muted">cov {s.coverage != null ? `${s.coverage.toFixed(1)}%` : "—"}</span>
                  <span className="px-1 py-0.5 rounded bg-accent/15 border border-accent/30 text-[10px] text-accent">score {s.selection_score != null ? s.selection_score.toFixed(3) : "—"}</span>
                </div>
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
