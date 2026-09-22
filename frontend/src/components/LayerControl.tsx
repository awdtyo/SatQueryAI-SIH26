interface LayerVisibility {
  aoi: boolean;
  footprints: boolean;
  selected: boolean;
  preview: boolean;
  analysis: boolean;
}

interface Props {
  visibility: LayerVisibility;
  onChange: (next: LayerVisibility) => void;
  hasAnalysis?: boolean;
  hasPreview?: boolean;
}

export default function LayerControl({ visibility, onChange, hasAnalysis = false, hasPreview = false }: Props) {
  const toggle = (key: keyof LayerVisibility) => {
    onChange({ ...visibility, [key]: !visibility[key] });
  };

  return (
    <div className="panel p-3">
      <div className="text-[11px] font-semibold text-accent tracking-[0.08em] uppercase mb-2">Layers</div>
      <div className="space-y-2">
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" checked={visibility.aoi} onChange={() => toggle("aoi")} className="accent-accent" />
          <span className="text-[12px] text-ink">AOI</span>
        </label>
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" checked={visibility.footprints} onChange={() => toggle("footprints")} className="accent-accent" />
          <span className="text-[12px] text-ink">Scene footprints</span>
        </label>
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" checked={visibility.selected} onChange={() => toggle("selected")} className="accent-accent" />
          <span className="text-[12px] text-ink">Selected scene</span>
        </label>
        <label className={`flex items-center gap-2 ${hasPreview ? "cursor-pointer" : "opacity-50 cursor-not-allowed"}`}>
          <input type="checkbox" checked={visibility.preview} onChange={() => hasPreview && toggle("preview")} disabled={!hasPreview} className="accent-accent" />
          <span className="text-[12px] text-ink">Satellite preview</span>
          {!hasPreview && <span className="text-[10px] text-ink-muted">(no preview)</span>}
        </label>
        <label className={`flex items-center gap-2 ${hasAnalysis ? "cursor-pointer" : "opacity-50 cursor-not-allowed"}`}>
          <input type="checkbox" checked={visibility.analysis} onChange={() => hasAnalysis && toggle("analysis")} disabled={!hasAnalysis} className="accent-accent" />
          <span className="text-[12px] text-ink">Analysis output</span>
          {!hasAnalysis && <span className="text-[10px] text-ink-muted">(no analysis)</span>}
        </label>
      </div>
      <div className="mt-3 text-[10px] text-ink-muted">
        Future: RGB, false color, NDVI/NDWI/NDBI, SAR, change, detections. Current shows real data only.
      </div>
    </div>
  );
}

export type { LayerVisibility };
