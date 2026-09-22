export interface SatelliteScene {
  id: string;
  collection: string;
  datetime: string | null;
  platform: string | null;
  processing_level: string | null;
  cloud_cover: number | null;
  geometry: Record<string, unknown> | null;
  bbox: number[] | null;
  coverage: number | null;
  selection_score: number | null;
  thumbnail: string | null;
  assets: Record<string, string>;
  metadata: Record<string, unknown>;
  provider: string;
}
