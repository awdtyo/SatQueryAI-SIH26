import type { UploadedImage } from "../types/api";
import { formatCollection, isResolvedScene, sceneIdentity } from "../lib/imageMeta";

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatTimestamp(file: File): string {
  const stamp = file.lastModified;
  if (!stamp) return "timestamp unavailable";
  return new Date(stamp).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

interface LoadedFileCardProps {
  image: UploadedImage;
  slotLabel: string;
  onRemove: () => void;
}

/**
 * Compact card for a loaded scene.
 *
 * A genuine upload shows the browser's own facts about the file. A scene the
 * backend resolved from a location query instead shows its STAC identity and
 * collection — its `File` is a synthetic wrapper around a base64 preview, so the
 * wrapper's name, byte count and "now" modification time are not facts about the
 * scene and are not shown.
 */
export default function LoadedFileCard({ image, slotLabel, onRemove }: LoadedFileCardProps) {
  const identity = sceneIdentity(image);
  const resolved = isResolvedScene(image);
  const collection = formatCollection(image.meta?.collection);

  return (
    <article className="flex items-center gap-3 rounded-lg border border-slate-800 bg-slate-950 p-2.5 transition-colors duration-150 hover:border-slate-700">
      <div className="relative h-11 w-11 flex-shrink-0 overflow-hidden rounded-md border border-slate-800 bg-slate-900">
        <img src={image.preview} alt="" className="h-full w-full object-cover" />
        <span
          className="absolute -bottom-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full
            border border-emerald-500/30 bg-slate-950 text-emerald-400"
          title={resolved ? "Resolved from archive" : "Loaded"}
        >
          <svg width="9" height="9" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path
              d="M3.5 8.5l3 3 6-6"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <span className="sr-only">
            {resolved ? "Resolved from the satellite archive" : "Loaded successfully"}
          </span>
        </span>
      </div>

      <div className="min-w-0 flex-1">
        <span className="block text-[10px] font-semibold uppercase tracking-wider text-teal-300">
          {slotLabel}
        </span>
        <p className="truncate text-[12px] text-slate-200" title={identity}>
          {identity}
        </p>
        <p className="text-[10px] tabular-nums text-slate-500">
          {resolved
            ? (collection ?? "satellite archive")
            : `${formatFileSize(image.file.size)} · ${formatTimestamp(image.file)}`}
        </p>
      </div>

      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove ${identity}`}
        title={`Remove ${identity}`}
        className="icon-btn hover:bg-rose-500/10 hover:text-rose-400"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
          <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
        </svg>
      </button>
    </article>
  );
}
