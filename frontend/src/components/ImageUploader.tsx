import { useCallback, useRef, useState } from "react";
import type { InputMode, UploadedImage } from "../types/api";
import InputModeTabs, { INPUT_MODES } from "./InputModeTabs";
import FileDropzone, { FormatChips } from "./FileDropzone";
import LoadedFileCard from "./LoadedFileCard";

const ACCEPTED_EXTENSIONS = ".tif,.tiff,.png,.jpg,.jpeg";

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
  const draggingSlotRef = useRef<number | null>(null);

  const currentMode = INPUT_MODES.find((m) => m.key === inputMode)!;

  const setDraggingSlot = useCallback((slot: number | null) => {
    draggingSlotRef.current = slot;
    setIsDragging(slot !== null);
  }, []);

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
        // Fixed-length array indexed by slot — guarantees T1=0, T2=1 order regardless of fill order.
        const next = [...prev];
        // Ensure length covers all slots so indexed assignment is stable.
        while (next.length < currentMode.slots) next.push(undefined as unknown as UploadedImage);
        const existing = next[slotIndex];
        if (existing?.preview) URL.revokeObjectURL(existing.preview);
        next[slotIndex] = newImage;
        // Trim trailing undefined (should not happen after fill, but keep compact)
        return next.filter(Boolean);
      });
    },
    [inputMode, currentMode, setImages],
  );

  const handleDrop = useCallback(
    (event: React.DragEvent, slotIndex: number) => {
      event.preventDefault();
      setDraggingSlot(null);
      setActiveSlot(slotIndex);
      handleFiles(event.dataTransfer.files, slotIndex);
    },
    [handleFiles, setDraggingSlot],
  );

  const handleDragLeave = useCallback(
    (event: React.DragEvent, slotIndex: number) => {
      // Ignore dragleave events fired while moving between the dropzone's own children.
      const next = event.relatedTarget as Node | null;
      if (next && event.currentTarget.contains(next)) return;
      if (draggingSlotRef.current === slotIndex) setDraggingSlot(null);
    },
    [setDraggingSlot],
  );

  const removeImage = useCallback(
    (slotIndex: number) => {
      setImages((prev) => {
        const next = [...prev];
        const img = next[slotIndex];
        if (img?.preview) URL.revokeObjectURL(img.preview);
        // Keep slot ordering — replace with undefined and compact only trailing holes.
        next.splice(slotIndex, 1);
        return next.filter(Boolean);
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

  const browse = useCallback(() => fileInputRef.current?.click(), []);

  return (
    <div className="space-y-3">
      <InputModeTabs value={inputMode} onChange={handleModeChange} />

      <div className={`grid gap-2 ${currentMode.slots === 1 ? "grid-cols-1" : "grid-cols-2"}`}>
        {currentMode.slotLabels.map((slotLabel, idx) => {
          const image = images[idx];
          return image ? (
            <LoadedFileCard
              key={`${inputMode}-${idx}`}
              image={image}
              slotLabel={slotLabel}
              onRemove={() => removeImage(idx)}
            />
          ) : (
            <FileDropzone
              key={`${inputMode}-${idx}`}
              slotLabel={slotLabel}
              dragging={isDragging && activeSlot === idx}
              onActivate={() => setActiveSlot(idx)}
              onDragEnter={() => {
                setActiveSlot(idx);
                setDraggingSlot(idx);
              }}
              onDragLeave={(event) => handleDragLeave(event, idx)}
              onDrop={(event) => handleDrop(event, idx)}
              onBrowse={browse}
            />
          );
        })}
      </div>

      <FormatChips />

      <input
        ref={fileInputRef}
        type="file"
        accept={ACCEPTED_EXTENSIONS}
        className="hidden"
        onChange={(e) => handleFiles(e.target.files, activeSlot)}
      />

      {images.length > 0 && (
        <div className="flex items-center justify-between text-[11px]">
          <span className="flex items-center gap-1.5 text-slate-400">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" aria-hidden="true" />
            {images.length} file{images.length !== 1 ? "s" : ""} loaded
          </span>
          {currentMode.slots === 2 && images.length < currentMode.slots && (
            <span className="text-amber-400">
              {currentMode.slots - images.length} slot
              {currentMode.slots - images.length > 1 ? "s" : ""} empty
            </span>
          )}
        </div>
      )}
    </div>
  );
}
