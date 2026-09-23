import type { DragEvent, KeyboardEvent } from "react";
import { IconUpload } from "./icons";

interface Props {
  label: string;
  hint: string;
  isDragActive: boolean;
  onBrowse: () => void;
  onDragActive: (active: boolean) => void;
  onDrop: (e: DragEvent) => void;
}

const SUPPORTED_FORMATS = ["GeoTIFF", "TIFF", "PNG", "JPEG"];

export default function FileDropzone({ label, hint, isDragActive, onBrowse, onDragActive, onDrop }: Props) {
  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onBrowse();
    }
  };

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`Upload ${label}`}
      onClick={onBrowse}
      onKeyDown={handleKeyDown}
      onDragOver={(e) => {
        e.preventDefault();
        onDragActive(true);
      }}
      onDragLeave={() => onDragActive(false)}
      onDrop={(e) => {
        e.preventDefault();
        onDragActive(false);
        onDrop(e);
      }}
      className={`group flex cursor-pointer flex-col items-center justify-center gap-2.5 rounded-lg border-2 border-dashed px-3 py-4 text-center outline-none transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-teal-500/60 ${
        isDragActive
          ? "border-teal-400/70 bg-teal-500/10"
          : "border-slate-700 bg-slate-950/50 hover:border-teal-500/50 hover:bg-slate-950"
      }`}
    >
      <div className="flex h-9 w-9 items-center justify-center rounded-md border border-slate-700 bg-slate-800 text-teal-400 transition-colors group-hover:text-teal-300">
        <IconUpload />
      </div>
      <div>
        <p className="text-[12px] font-medium text-slate-200">{label}</p>
        <p className={`mt-0.5 text-[11px] ${isDragActive ? "text-teal-300" : "text-slate-400"}`}>
          {isDragActive ? "Release to load imagery" : hint}
        </p>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-1">
        {SUPPORTED_FORMATS.map((format) => (
          <span
            key={format}
            className="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wider text-slate-500"
          >
            {format}
          </span>
        ))}
      </div>
    </div>
  );
}