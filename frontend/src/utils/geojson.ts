import type { SatelliteScene } from "../types/satellite";

export function isValidGeoJSON(geom: unknown): boolean {
  if (!geom || typeof geom !== "object") return false;
  const g = geom as Record<string, unknown>;
  const type = g.type as string;
  if (!["Polygon", "MultiPolygon", "Feature", "FeatureCollection", "Point"].includes(type)) return false;
  // Check coordinates exist for Polygon
  if (type === "Polygon") {
    const coords = g.coordinates as unknown;
    if (!Array.isArray(coords) || coords.length === 0) return false;
    // At least one ring with 4 points
    const ringRaw = (coords as unknown[])[0] as unknown[] | undefined;
    if (!ringRaw || !Array.isArray(ringRaw) || ringRaw.length < 4) return false;
    const ring = ringRaw as unknown[];
    // Check lon/lat order - each coordinate should be [lon, lat]
    for (const c of ring) {
      if (!Array.isArray(c as unknown[]) || (c as unknown[]).length < 2) return false;
      const lon = (c as number[])[0];
      const lat = (c as number[])[1];
      if (typeof lon !== "number" || typeof lat !== "number") return false;
      if (lon < -180 || lon > 180 || lat < -90 || lat > 90) return false;
    }
  }
  return true;
}

export function extractGeometry(geojson: Record<string, unknown>): Record<string, unknown> {
  const t = geojson.type as string;
  if (t === "Feature") {
    const g = (geojson as { geometry?: Record<string, unknown> }).geometry;
    return g || geojson;
  }
  if (t === "FeatureCollection") {
    const feats = (geojson as { features?: Array<{ geometry?: Record<string, unknown> }> }).features;
    if (feats && feats.length > 0) return feats[0]!.geometry || (feats[0]! as unknown as Record<string, unknown>);
  }
  return geojson;
}

export function getGeoJSONBounds(geojson: Record<string, unknown> | null): [[number, number], [number, number]] | null {
  if (!geojson) return null;
  try {
    const geom = extractGeometry(geojson);
    const coords = (geom as { coordinates?: unknown }).coordinates;
    if (!coords) return null;
    let minLon = 180,
      minLat = 90,
      maxLon = -180,
      maxLat = -90;
    const traverse = (c: unknown) => {
      if (Array.isArray(c) && typeof c[0] === "number" && typeof c[1] === "number") {
        const lon = c[0] as number;
        const lat = c[1] as number;
        minLon = Math.min(minLon, lon);
        minLat = Math.min(minLat, lat);
        maxLon = Math.max(maxLon, lon);
        maxLat = Math.max(maxLat, lat);
      } else if (Array.isArray(c)) {
        for (const sub of c) traverse(sub);
      }
    };
    traverse(coords);
    if (minLon === 180) return null;
    // Return as [[southWest], [northEast]] for Leaflet
    return [
      [minLat, minLon],
      [maxLat, maxLon],
    ];
  } catch {
    return null;
  }
}

export function getScenesBounds(scenes: SatelliteScene[]): [[number, number], [number, number]] | null {
  if (!scenes.length) return null;
  let minLon = 180,
    minLat = 90,
    maxLon = -180,
    maxLat = -90;
  let found = false;
  for (const s of scenes) {
    const geom = s.geometry as Record<string, unknown> | null;
    if (!geom) {
      // Fallback to bbox
      if (s.bbox && s.bbox.length === 4) {
        const west = s.bbox[0] as number;
        const south = s.bbox[1] as number;
        const east = s.bbox[2] as number;
        const north = s.bbox[3] as number;
        if ([west, south, east, north].every((v) => typeof v === "number")) {
          minLon = Math.min(minLon, west);
          minLat = Math.min(minLat, south);
          maxLon = Math.max(maxLon, east);
          maxLat = Math.max(maxLat, north);
          found = true;
        }
      }
      continue;
    }
    const b = getGeoJSONBounds(geom);
    if (b) {
      minLon = Math.min(minLon, b[0][1]);
      minLat = Math.min(minLat, b[0][0]);
      maxLon = Math.max(maxLon, b[1][1]);
      maxLat = Math.max(maxLat, b[1][0]);
      found = true;
    } else if (s.bbox && s.bbox.length === 4) {
      const west = s.bbox[0] as number;
      const south = s.bbox[1] as number;
      const east = s.bbox[2] as number;
      const north = s.bbox[3] as number;
      if ([west, south, east, north].every((v) => typeof v === "number")) {
        minLon = Math.min(minLon, west);
        minLat = Math.min(minLat, south);
        maxLon = Math.max(maxLon, east);
        maxLat = Math.max(maxLat, north);
        found = true;
      }
    }
  }
  if (!found) return null;
  return [
    [minLat, minLon],
    [maxLat, maxLon],
  ];
}

export function sceneToGeoJSON(scene: SatelliteScene): Record<string, unknown> | null {
  if (scene.geometry) return scene.geometry as Record<string, unknown>;
  if (scene.bbox && scene.bbox.length === 4) {
    const [west, south, east, north] = scene.bbox;
    return {
      type: "Polygon",
      coordinates: [
        [
          [west, south],
          [east, south],
          [east, north],
          [west, north],
          [west, south],
        ],
      ],
    };
  }
  return null;
}

export function formatGeoJSON(geom: Record<string, unknown> | null): string {
  if (!geom) return "";
  return JSON.stringify(geom, null, 2);
}
