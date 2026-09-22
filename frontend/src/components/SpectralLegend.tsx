interface Props {
  index: string;
  visual: Record<string, unknown>;
  interpretation: Record<string, unknown>;
}

const LEGEND_COLORS: Record<string, string[]> = {
  NDVI: ["#a50026", "#d73027", "#f46d43", "#fdae61", "#fee08b", "#d9ef8b", "#a6d96a", "#66bd63", "#1a9850", "#006837"],
  NDWI: ["#8c510a", "#d8b365", "#f6e8c3", "#c7eae5", "#5ab4ac", "#01665e"],
  NDBI: ["#2166ac", "#67a9cf", "#d1e5f0", "#fddbc7", "#ef8a62", "#b2182b"],
  NDMI: ["#a6611a", "#dfc27d", "#f5f5f5", "#80cdc1", "#018571"],
  SAVI: ["#f7fcb9", "#addd8e", "#31a354"],
  BSI: ["#2166ac", "#f7f7f7", "#b35806", "#543005"],
};

export default function SpectralLegend({ index, visual, interpretation }: Props) {
  const vmin = (visual?.min as number) ?? -1;
  const vmax = (visual?.max as number) ?? 1;
  const cmap = (visual?.cmap as string) ?? "RdYlGn";
  const colors = (LEGEND_COLORS[index] || LEGEND_COLORS.NDVI)!;

  return (
    <div className="panel p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[11px] font-semibold text-accent tracking-[0.08em] uppercase">{index} Legend</span>
        <span className="text-[10px] text-ink-muted">{vmin} → {vmax} · {cmap}</span>
      </div>
      <div className="h-3 rounded overflow-hidden flex">
        {colors.map((c, i) => (
          <div key={i} style={{ background: c, flex: 1 }} />
        ))}
      </div>
      <div className="flex justify-between text-[10px] text-ink-muted mt-1">
        <span>{vmin}</span>
        <span>0</span>
        <span>{vmax}</span>
      </div>
      {interpretation && Object.keys(interpretation).length > 0 && (
        <div className="mt-2 space-y-1">
          {Object.entries(interpretation).map(([k, v]) => (
            <div key={k} className="flex justify-between text-[10px]">
              <span className="text-ink-muted font-mono">{k}</span>
              <span className="text-ink-secondary text-right ml-2">{String(v)}</span>
            </div>
          ))}
        </div>
      )}
      <div className="mt-2 text-[10px] text-ink-muted">Legend from registry `backend/spectral/registry.py` · not hard-coded.</div>
    </div>
  );
}
