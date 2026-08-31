import { useCallback, useRef, useState } from "react";
import type { InputMode, UploadedImage } from "../types/api";

const ACCEPTED_EXTENSIONS = ".tif,.tiff,.png,.jpg,.jpeg";

const MODES: { key: InputMode; label: string; slots: number; slotLabels: string[]; description: string }[] = [
  {
    key: "single",
    label: "SINGLE",
    slots: 1,
    slotLabels: ["Image"],
    description: "Single optical or SAR image",
  },
  {
    key: "optical-sar",
    label: "OPTICAL+SAR",
    slots: 2,
    slotLabels: ["Optical", "SAR"],
    description: "Co-registered optical and SAR pair",
  },
  {
    key: "bi-temporal",
    label: "BI-TEMPORAL",
    slots: 2,
    slotLabels: ["Date 1 (T1)", "Date 2 (T2)"],
    description: "Same location, two different dates",
  },
];

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

interface Props {
  images: UploadedImage[];
  setImages: React.Dispatch<React.SetStateAction<UploadedImage[]>>;
  inputMode: InputMode;
  setInputMode: (mode: InputMode) => void;
}

export default function ImageUploader({ images, setImages, inputMode, setInputMode }: Props) {
  const [isDragging, setIsDragging] = useState(false);
  const [activeSlot, setActiveSlot] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const currentMode = MODES.find((m) => m.key === inputMode)!;

  const handleFiles = useCallback(
    (files: FileList | null, slotIndex: number) => {
      if (!files || files.length === 0) return;
      const file = files[0]!;

      const preview = URL.createObjectURL(file);
      const role =
        inputMode === "optical-sar"
          ? slotIndex === 0
            ? "optical"
            : "sar"
          : inputMode === "bi-temporal"
            ? slotIndex === 0
              ? "t1"
              : "t2"
            : undefined;

      const newImage: UploadedImage = {
        file,
        preview,
        label: currentMode.slotLabels[slotIndex] ?? `Slot ${slotIndex + 1}`,
        role,
      };

      setImages((prev) => {
        const next = [...prev];
        const existingIdx = next.findIndex(
          (img) => img.role === role && img.label === currentMode.slotLabels[slotIndex],
        );
        if (existingIdx >= 0) {
          URL.revokeObjectURL(next[existingIdx]!.preview);
          next.splice(existingIdx, 1);
        }
        next.splice(slotIndex, 0, newImage);
        return next;
      });
    },
    [inputMode, currentMode, setImages],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      handleFiles(e.dataTransfer.files, activeSlot);
    },
    [handleFiles, activeSlot],
  );

  const removeImage = useCallback(
    (slotIndex: number) => {
      setImages((prev) => {
        const next = [...prev];
        const img = next[slotIndex];
        if (img) URL.revokeObjectURL(img.preview);
        next.splice(slotIndex, 1);
        return next;
      });
    },
    [setImages],
  );

  const handleModeChange = useCallback(
    (newMode: InputMode) => {
      images.forEach((img) => URL.revokeObjectURL(img.preview));
      setImages([]);
      setInputMode(newMode);
      setActiveSlot(0);
    },
    [images, setImages, setInputMode],
  );

  return (
    <div className="space-y-4">
      {/* Mode selector */}
      <div>
        <label className="block text-[11px] font-medium text-ink-muted uppercase tracking-[0.1em] mb-2">
          Input Mode
        </label>
        <div className="flex bg-surface-900 border border-surface-400/40 rounded-lg overflow-hidden">
          {MODES.map((mode) => (
            <button
              key={mode.key}
              onClick={() => handleModeChange(mode.key)}
              className={`
                flex-1 px-2 py-2 text-[11px] font-medium tracking-wide transition-all duration-150
                ${
                  inputMode === mode.key
                      ? "bg-accent/10 text-accent"
                    : "text-ink-muted hover:text-ink-secondary"
                }
              `}
            >
              {mode.label}
            </button>
          ))}
        </div>
      </div>

      {/* Supported formats */}
      <p className="text-[11px] text-ink-muted">
        Supported: <span className="text-ink-secondary">GeoTIFF · TIFF · PNG · JPEG</span>
      </p>

      {/* Upload / preview area */}
      <div className={`grid gap-2.5 ${currentMode.slots === 1 ? "grid-cols-1" : "grid-cols-2"}`}>
        {currentMode.slotLabels.map((slotLabel, idx) => {
          const image = images[idx];
          return (
            <div
              key={`${inputMode}-${idx}`}
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragging(true);
                setActiveSlot(idx);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              onClick={() => {
                setActiveSlot(idx);
                fileInputRef.current?.click();
              }}
              className={`
                relative border cursor-pointer transition-colors duration-150 overflow-hidden rounded-lg
                ${
                  image
                    ? "border-surface-400/40 bg-surface-700/30"
                    : isDragging && activeSlot === idx
                      ? "border-accent/50 bg-accent/5"
                      : "border-dashed border-surface-400/40 bg-surface-900/40 hover:border-accent/40"
                }
              `}
            >
              {image ? (
                <div className="relative group">
                  <img
                    src={image.preview}
                    alt={image.label}
                    className="w-full h-28 object-cover opacity-90 group-hover:opacity-100 transition-opacity"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-surface-900 via-surface-900/20 to-transparent" />
                  <div className="absolute top-2 right-2">
                    <span className="w-2 h-2 rounded-full bg-signal-green block" />
                  </div>
                  <div className="absolute bottom-0 left-0 right-0 px-2 pb-1.5 pt-6">
                    <div className="flex items-end justify-between">
                      <div className="min-w-0">
                        <div className="text-[11px] font-medium text-accent">
                          {slotLabel.toUpperCase()}
                        </div>
                        <div className="text-[10px] text-ink-secondary truncate">
                          {image.file.name.slice(0, 28)}
                        </div>
                        <div className="text-[10px] text-ink-muted">
                          {formatFileSize(image.file.size)}
                        </div>
                      </div>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          removeImage(idx);
                        }}
                        className="text-[10px] font-medium text-signal-red/60 hover:text-signal-red transition-colors flex-shrink-0 ml-1"
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-28 gap-2 px-2 text-center">
                  <svg
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.2"
                    className="text-ink-muted"
                  >
                    <rect x="3" y="3" width="18" height="18" rx="2" />
                    <circle cx="9" cy="9" r="1.5" fill="currentColor" />
                    <path d="M21 15l-5-5L5 21" />
                  </svg>
                  <span className="text-[11px] text-ink-secondary">
                    {isDragging && activeSlot === idx
                      ? "Drop here"
                      : currentMode.slots === 1
                        ? "Drop image or Browse"
                        : `Drop ${slotLabel} or Browse`}
                  </span>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept={ACCEPTED_EXTENSIONS}
        className="hidden"
        onChange={(e) => handleFiles(e.target.files, activeSlot)}
      />

      {/* Status */}
      {images.length > 0 && (
        <div className="flex items-center justify-between text-[11px]">
          <div className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-signal-green" />
            <span className="text-ink-secondary">
              {images.length} file{images.length !== 1 ? "s" : ""} loaded
            </span>
          </div>
          {currentMode.slots === 2 && images.length < currentMode.slots && (
            <span className="text-signal-amber">
              {currentMode.slots - images.length} slot{currentMode.slots - images.length > 1 ? "s" : ""} empty
            </span>
          )}
        </div>
      )}
    </div>
  );
}
