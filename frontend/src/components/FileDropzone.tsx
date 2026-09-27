const FORMATS = ["GeoTIFF", "TIFF", "PNG", "JPEG"] as const;

/** Small chips listing the accepted upload formats. */
export function FormatChips() {
  return (
    <ul className="flex flex-wrap items-center gap-1.5" aria-label="Supported file formats">
      {FORMATS.map((format) => (
        <li
          key={format}
          className="rounded-md border border-slate-800 bg-slate-950 px-1.5 py-0.5
            text-[10px] font-medium uppercase tracking-wider text-slate-500"
        >
          {format}
        </li>
      ))}
    </ul>
  );
}

interface FileDropzoneProps {
  /** Slot caption, e.g. "Optical" or "Date 1 (T1)". */
  slotLabel: string;
  /** True while a dragged file is hovering this specific slot. */
  dragging: boolean;
  onActivate: () => void;
  onDragEnter: () => void;
  onDragLeave: (event: React.DragEvent) => void;
  onDrop: (event: React.DragEvent) => void;
  onBrowse: () => void;
}

/** Dashed drop target for a single imagery slot. */
export default function FileDropzone({
  slotLabel,
  dragging,
  onActivate,
  onDragEnter,
  onDragLeave,
  onDrop,
  onBrowse,
}: FileDropzoneProps) {
  return (
    <button
      type="button"
      onClick={() => {
        onActivate();
        onBrowse();
      }}
      onDragOver={(event) => {
        event.preventDefault();
        onDragEnter();
      }}
      onDragEnter={(event) => {
        event.preventDefault();
        onDragEnter();
      }}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      aria-label={`Upload ${slotLabel} — drop a file here or browse`}
      className={[
        "flex h-32 w-full flex-col items-center justify-center gap-2 rounded-lg border border-dashed",
        "px-3 text-center transition-colors duration-150",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/50",
        dragging
          ? "border-teal-500/60 bg-teal-500/10"
          : "border-slate-700 bg-slate-950 hover:border-teal-500/40 hover:bg-slate-900",
      ].join(" ")}
    >
      <span
        className={`flex h-9 w-9 items-center justify-center rounded-lg border transition-colors duration-150 ${
          dragging
            ? "border-teal-500/40 bg-teal-500/10 text-teal-300"
            : "border-slate-800 bg-slate-900 text-slate-500"
        }`}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
          <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M4 15v3a2 2 0 002 2h12a2 2 0 002-2v-3" strokeLinecap="round" />
        </svg>
      </span>

      <span className="text-[11px] font-medium text-slate-400">
        {dragging ? `Drop ${slotLabel} here` : `Drop ${slotLabel} or browse`}
      </span>
    </button>
  );
}
