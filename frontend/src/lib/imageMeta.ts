/**
 * Formatting helpers for imagery metadata.
 *
 * Every helper here takes a real value that the browser or the backend actually
 * produced. None of them substitutes a plausible default — a caller that has no
 * value must not call, and `describeImage` omits rows it cannot fill rather
 * than inventing resolution, band or sensor metadata.
 */

import type { UploadedImage } from "../types/api";

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Local wall-clock time from the file's own `lastModified`. */
export function formatFileTime(file: File): string | null {
  const stamp = file.lastModified;
  if (!stamp) return null;
  return new Date(stamp).toLocaleString([], {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Human label for a STAC collection id, e.g. `sentinel-2-l2a` → `Sentinel-2 L2A`. */
export function formatCollection(collection: string | undefined): string | null {
  if (!collection) return null;
  const known: Record<string, string> = {
    "sentinel-2-l2a": "Sentinel-2 L2A",
    "sentinel-1-rtc": "Sentinel-1 RTC",
  };
  const id = collection.toLowerCase();
  return known[id] ?? collection;
}

/** Signed decimal degrees, only when both values exist. */
export function formatCoords(lat: number | undefined, lon: number | undefined): string | null {
  if (typeof lat !== "number" || typeof lon !== "number") return null;
  if (Number.isNaN(lat) || Number.isNaN(lon)) return null;
  const ns = lat >= 0 ? "N" : "S";
  const ew = lon >= 0 ? "E" : "W";
  return `${Math.abs(lat).toFixed(4)}°${ns}  ${Math.abs(lon).toFixed(4)}°${ew}`;
}

/** Sensor or producer implied by the file's own MIME type. */
export function formatMedia(file: File): string | null {
  const type = file.type?.toLowerCase() ?? "";
  if (!type) return null;
  if (type.includes("tiff")) return "GeoTIFF / TIFF";
  if (type.includes("png")) return "PNG";
  if (type.includes("jpeg") || type.includes("jpg")) return "JPEG";
  return type;
}

export interface MetaRow {
  label: string;
  value: string;
  /** Long values get their own line in the HUD. */
  wide?: boolean;
}

/**
 * How a scene should be named in the interface.
 *
 * For a location-resolved scene the real identity is the STAC scene id, or the
 * place name the backend geocoded to. The local `File` in that case is a
 * synthetic wrapper the app built from a base64 preview, so its name, size and
 * timestamp say nothing about the actual scene and must never be shown. A real
 * upload has no STAC provenance, so its own filename is the honest label.
 */
export function sceneIdentity(image: UploadedImage): string {
  const meta = image.meta;
  if (meta?.scene_id) return meta.scene_id;
  if (meta?.display_name) return meta.display_name;
  if (meta?.collection) return meta.collection;
  return image.file?.name ?? "Scene";
}

/** True when the backend resolved this scene from a location query. */
export function isResolvedScene(image: UploadedImage): boolean {
  return Boolean(image.meta?.scene_id || image.meta?.collection || image.meta?.display_name);
}

/**
 * Build the HUD rows for one image from real values only.
 *
 * Order of preference: STAC provenance from the backend (collection, scene id,
 * coordinates) when the scene was resolved from a location, otherwise the
 * browser's own facts about the file (media type, byte size, modified time).
 * The two sets are never mixed — a resolved scene's `File` is a synthetic
 * wrapper around a base64 preview, so its size, MIME type and modification time
 * are artefacts of the wrapper and not facts about the scene.
 * Fields we cannot know — spatial resolution, band count, sensor, cloud cover
 * for uploads — are simply absent.
 */
export function describeImage(image: UploadedImage): MetaRow[] {
  const rows: MetaRow[] = [];
  const { meta, file } = image;

  if (isResolvedScene(image)) {
    const collection = formatCollection(meta?.collection);
    if (collection) rows.push({ label: "Collection", value: collection });

    const coords = formatCoords(meta?.lat, meta?.lon);
    if (coords) rows.push({ label: "Centre", value: coords });

    if (meta?.scene_id) rows.push({ label: "Scene", value: meta.scene_id, wide: true });

    return rows;
  }

  const media = formatMedia(file);
  if (media) rows.push({ label: "Format", value: media });

  if (file.size > 0) rows.push({ label: "Size", value: formatBytes(file.size) });

  const time = formatFileTime(file);
  if (time) rows.push({ label: "Modified", value: time });

  return rows;
}
