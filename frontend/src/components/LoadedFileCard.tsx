import type { UploadedImage } from "../types/api";
import { formatFileSize, formatFileTime } from "../utils/format";
import { IconCheck, IconClose } from "./icons";

interface Props {
  image: UploadedImage;
  roleLabel: string;
  onRemove: () => void;
}

export default function LoadedFileCard({ image, roleLabel, onRemove }: Props) {
  return (
    <div className="group flex items-center gap-3 rounded-lg border border-slate-800 bg-slate-900 p-2">
      <div className="h-11 w-11 flex-shrink-0 overflow-hidden rounded-md border border-slate-700">
        <img src={image.preview} alt={image.label} className="h-full w-full object-cover" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[11px] font-medium text-slate-200">{image.file.name}</p>
        <div className="mt-0.5 flex items-center gap-2">
          <span className="text-[9px] font-semibold uppercase tracking-wider text-teal-400">{roleLabel}</span>
          <span className="text-[10px] tabular-nums text-slate-500">{formatFileTime(image.file.lastModified)}</span>
          <span className="text-[10px] text-slate-500">{formatFileSize(image.file.size)}</span>
        </div>
      </div>
      <div className="flex flex-shrink-0 items-center gap-1.5">
        <span className="flex h-5 w-5 items-center justify-center rounded-full border border-emerald-500/30 bg-emerald-500/15 text-emerald-400">
          <IconCheck />
        </span>
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove ${image.file.name}`}
          className="rounded p-1 text-slate-500 opacity-0 transition-opacity hover:text-rose-400 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/60 group-hover:opacity-100"
        >
          <IconClose />
        </button>
      </div>
    </div>
  );
}