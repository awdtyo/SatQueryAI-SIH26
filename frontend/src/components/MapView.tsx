import { useEffect, useRef, useMemo, useCallback } from "react";
import { MapContainer, TileLayer, GeoJSON, ImageOverlay, useMap, useMapEvents } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "leaflet-draw/dist/leaflet.draw.css";
import type { SatelliteScene } from "../types/satellite";
import { getGeoJSONBounds, getScenesBounds, sceneToGeoJSON, extractGeometry } from "../utils/geojson";

// Fix default icon paths for Leaflet
// eslint-disable-next-line @typescript-eslint/no-explicit-any
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

type DrawMode = "rectangle" | "polygon" | null;

interface LayerVisibility {
  aoi: boolean;
  footprints: boolean;
  selected: boolean;
  preview: boolean;
  analysis: boolean;
}

interface SpectralLayer {
  preview_b64: string | null;
  bounds: [[number, number], [number, number]] | null;
  opacity: number;
  visible: boolean;
  index: string;
}

interface Props {
  aoiGeometry: Record<string, unknown> | null;
  scenes: SatelliteScene[];
  selectedSceneId: string | null;
  onAoiChange: (geom: Record<string, unknown> | null) => void;
  onSceneSelect: (id: string) => void;
  layerVisibility: LayerVisibility;
  drawMode: DrawMode;
  onDrawModeChange: (mode: DrawMode) => void;
  spectralLayer?: SpectralLayer | null;
  onMapClick?: (lat: number, lon: number) => void;
}

// Helper to fit bounds when aoi/scenes/spectral change
function FitBounds({ aoi, scenes, spectralBounds }: { aoi: Record<string, unknown> | null; scenes: SatelliteScene[]; spectralBounds?: [[number, number], [number, number]] | null }) {
  const map = useMap();
  const prevKeyRef = useRef<string>("");

  useEffect(() => {
    const key = JSON.stringify([aoi, scenes.map((s) => s.id).join(","), spectralBounds]);
    if (key === prevKeyRef.current) return;
    prevKeyRef.current = key;

    if (spectralBounds) {
      map.fitBounds(spectralBounds, { padding: [20, 20], maxZoom: 13 });
      return;
    }
    if (scenes.length > 0) {
      const b = getScenesBounds(scenes);
      if (b) {
        map.fitBounds(b, { padding: [20, 20], maxZoom: 12 });
        return;
      }
    }
    if (aoi) {
      const b = getGeoJSONBounds(aoi);
      if (b) {
        map.fitBounds(b, { padding: [30, 30], maxZoom: 11 });
        return;
      }
    }
    // No AOI/scenes: stay at world/India view (initial)
  }, [aoi, scenes, spectralBounds, map]);

  return null;
}

function MapClickHandler({ onMapClick }: { onMapClick?: (lat: number, lon: number) => void }) {
  useMapEvents({
    click(e) {
      if (onMapClick) onMapClick(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

// Drawing handler using Leaflet Draw
function DrawHandler({ mode, onAoiChange, onModeChange }: { mode: DrawMode; onAoiChange: (g: Record<string, unknown> | null) => void; onModeChange: (m: DrawMode) => void }) {
  const map = useMap();
  const drawnRef = useRef<L.FeatureGroup | null>(null);

  useEffect(() => {
    if (!drawnRef.current) {
      drawnRef.current = new L.FeatureGroup();
      map.addLayer(drawnRef.current);
    }
    const fg = drawnRef.current;

    // Clean up previous handlers
    const cleanup = () => {
      // Remove any active draw handler
      // Leaflet Draw stores handlers on map
      try {
        // @ts-ignore
        if (map._drawHandler) {
          // @ts-ignore
          map._drawHandler.disable();
          // @ts-ignore
          map._drawHandler = null;
        }
      } catch {}
    };

    if (!mode) {
      cleanup();
      return;
    }

    // Dynamically import leaflet-draw to avoid SSR issues
    import("leaflet-draw").then(() => {
      cleanup();
      let handler: unknown = null;
      if (mode === "rectangle") {
        // @ts-ignore - Leaflet Draw types
        handler = new L.Draw.Rectangle(map, {
          shapeOptions: { color: "#32D7FF", weight: 2, fillOpacity: 0.15 },
        });
      } else if (mode === "polygon") {
        // @ts-ignore
        handler = new L.Draw.Polygon(map, {
          shapeOptions: { color: "#32D7FF", weight: 2, fillOpacity: 0.15 },
          allowIntersection: false,
          showArea: true,
        });
      }
      if (handler) {
        // @ts-ignore
        map._drawHandler = handler;
        // @ts-ignore
        handler.enable();
      }

      const onCreated = (e: L.LeafletEvent & { layer: L.Layer }) => {
        const layer = e.layer as L.Polygon | L.Rectangle;
        const geojson = (layer as unknown as { toGeoJSON: () => { geometry: Record<string, unknown> } }).toGeoJSON();
        const geom = geojson.geometry;
        // Validate lon/lat order already via GeoJSON
        fg.clearLayers();
        fg.addLayer(layer as L.Layer);
        onAoiChange(geom);
        onModeChange(null);
        // Disable handler
        try {
          // @ts-ignore
          if (handler && (handler as { disable: () => void }).disable) (handler as { disable: () => void }).disable();
        } catch {}
      };

      map.on(L.Draw.Event.CREATED, onCreated as unknown as L.LeafletEventHandlerFn);
      return () => {
        map.off(L.Draw.Event.CREATED, onCreated as unknown as L.LeafletEventHandlerFn);
        try {
          // @ts-ignore
          if (handler && (handler as { disable: () => void }).disable) (handler as { disable: () => void }).disable();
        } catch {}
      };
    });

    return () => {
      cleanup();
    };
  }, [mode, map, onAoiChange, onModeChange]);

  return null;
}

export default function MapView({ aoiGeometry, scenes, selectedSceneId, onAoiChange, onSceneSelect, layerVisibility, drawMode, onDrawModeChange, spectralLayer, onMapClick }: Props) {
  const aoiStyle = useMemo(
    () => ({
      color: "#32D7FF",
      weight: 2,
      fillColor: "#32D7FF",
      fillOpacity: 0.12,
      dashArray: "6 4",
    }),
    []
  );

  const getSceneStyle = useCallback(
    (sceneId: string) => {
      const isSelected = sceneId === selectedSceneId;
      if (isSelected && layerVisibility.selected) {
        return { color: "#F4C95D", weight: 3, fillColor: "#F4C95D", fillOpacity: 0.18 };
      }
      if (!layerVisibility.footprints) return { opacity: 0, fillOpacity: 0 };
      return { color: "#35D58A", weight: 1.5, fillColor: "#35D58A", fillOpacity: 0.08 };
    },
    [selectedSceneId, layerVisibility]
  );

  const handleSceneClick = useCallback(
    (id: string) => {
      onSceneSelect(id);
    },
    [onSceneSelect]
  );

  // India/world initial view
  const initialCenter: [number, number] = [22.5, 78.5];
  const initialZoom = 4;

  return (
    <div className="relative w-full h-full min-h-[380px] rounded-lg overflow-hidden border border-surface-400/50 bg-surface-950">
      <MapContainer center={initialCenter} zoom={initialZoom} style={{ height: "100%", width: "100%" }} zoomControl={true} scrollWheelZoom={true}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FitBounds aoi={aoiGeometry} scenes={scenes} spectralBounds={spectralLayer?.visible ? spectralLayer.bounds : null} />
        <DrawHandler mode={drawMode} onAoiChange={onAoiChange} onModeChange={onDrawModeChange} />
        <MapClickHandler onMapClick={onMapClick} />

        {spectralLayer?.visible && spectralLayer.preview_b64 && spectralLayer.bounds && (
          <ImageOverlay url={spectralLayer.preview_b64} bounds={spectralLayer.bounds} opacity={spectralLayer.opacity} />
        )}

        {layerVisibility.aoi && aoiGeometry && (
          <GeoJSON
            key={`aoi-${JSON.stringify(aoiGeometry).slice(0, 80)}`}
            data={extractGeometry(aoiGeometry) as unknown as GeoJSON.GeoJsonObject}
            style={aoiStyle}
          />
        )}

        {scenes.map((scene) => {
          const geom = sceneToGeoJSON(scene);
          if (!geom) return null;
          const isSelected = scene.id === selectedSceneId;
          // If it's selected and selected layer hidden, don't show
          if (isSelected && !layerVisibility.selected) return null;
          // If not selected and footprints hidden, don't show
          if (!isSelected && !layerVisibility.footprints) return null;

          return (
            <GeoJSON
              key={scene.id}
              data={geom as unknown as GeoJSON.GeoJsonObject}
              style={getSceneStyle(scene.id)}
              eventHandlers={{
                click: () => handleSceneClick(scene.id),
              }}
            />
          );
        })}
      </MapContainer>

      {/* Drawing toolbar overlay */}
      <div className="absolute top-2 left-12 z-[400] flex gap-1 bg-surface-800/95 border border-surface-400/40 rounded-lg p-1.5 shadow-lg">
        <button
          onClick={() => onDrawModeChange(drawMode === "rectangle" ? null : "rectangle")}
          className={`px-2.5 py-1.5 text-[11px] font-medium rounded transition-colors ${drawMode === "rectangle" ? "bg-accent text-surface-900" : "bg-surface-700 text-ink hover:bg-surface-600"}`}
          title="Draw rectangular AOI"
        >
          ▭ Rectangle
        </button>
        <button
          onClick={() => onDrawModeChange(drawMode === "polygon" ? null : "polygon")}
          className={`px-2.5 py-1.5 text-[11px] font-medium rounded transition-colors ${drawMode === "polygon" ? "bg-accent text-surface-900" : "bg-surface-700 text-ink hover:bg-surface-600"}`}
          title="Draw polygonal AOI"
        >
          ⬠ Polygon
        </button>
        <button
          onClick={() => onAoiChange(null)}
          className="px-2.5 py-1.5 text-[11px] font-medium rounded bg-surface-700 text-ink hover:bg-signal-red/20 hover:text-signal-red transition-colors"
          title="Clear AOI"
        >
          ✕ Clear
        </button>
      </div>

      {/* Bottom toolbar: fit info (auto-fit already handles AOI/scenes) */}
      <div className="absolute bottom-2 left-2 z-[400] flex gap-1">
        <div className="px-2 py-1 rounded bg-surface-800/95 border border-surface-400/40 text-[10px] text-ink-muted">Auto-fit on AOI / scenes</div>
      </div>

      {/* Layer visibility indicator */}
      <div className="absolute top-2 right-2 z-[400] bg-surface-800/95 border border-surface-400/40 rounded-lg px-2 py-1.5 text-[10px] text-ink-muted max-w-[60%] truncate">
        {aoiGeometry ? "AOI ✓" : "No AOI"} · {scenes.length} scenes
        {spectralLayer?.visible && spectralLayer.preview_b64 && <span className="ml-2 text-accent">{spectralLayer.index} ✓</span>}
        {drawMode && <span className="ml-2 text-accent">Drawing {drawMode}…</span>}
      </div>
    </div>
  );
}
