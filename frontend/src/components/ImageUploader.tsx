import { useCallback, useRef, useState } from "react";
import type { DragEvent } from "react";
import type { InputMode, UploadedImage } from "../types/api";
import { ACCEPTED_EXTENSIONS, inputModeOption } from "../lib/inputModes";
import FileDropzone from "./FileDropzone";
import InputModeTabs from "./InputModeTabs";
import LoadedFileCard from "./LoadedFileCard";

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

  const currentMode = inputModeOption(inputMode);

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
    (event: DragEvent<HTMLElement>, slotIndex: number) => {
      event.preventDefault();
      setIsDragging(false);
      setActiveSlot(slotIndex);
      handleFiles(event.dataTransfer.files, slotIndex);
    },
    [handleFiles],
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

  const openPicker = useCallback((slotIndex: number) => {
    setActiveSlot(slotIndex);
    fileInputRef.current?.click();
  }, []);

  const handleModeChange = useCallback(
    (newMode: InputMode) => {
      images.forEach((img) => URL.revokeObjectURL(img.preview));
      setImages([]);
      setInputMode(newMode);
      setActiveSlot(0);
    },
    [images, setImages, setInputMode],
  );

  const emptySlots = currentMode.slots - images.length;

  return (
    <div className="space-y-4">
      <InputModeTabs inputMode={inputMode} onChange={handleModeChange} />

      <div className="space-y-2.5">
        {currentMode.slotLabels.map((slotLabel, idx) => {
          const image = images[idx];
          return image ? (
            <LoadedFileCard
              key={`${inputMode}-${idx}`}
              image={image}
              slotLabel={slotLabel}
              onRemove={() => removeImage(idx)}
              onReplace={() => openPicker(idx)}
            />
          ) : (
            <FileDropzone
              key={`${inputMode}-${idx}`}
              slotLabel={slotLabel}
              isDragActive={isDragging && activeSlot === idx}
              onDragEnter={() => {
                setIsDragging(true);
                setActiveSlot(idx);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={(event) => handleDrop(event, idx)}
              onSelect={() => openPicker(idx)}
            />
          );
        })}
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept={ACCEPTED_EXTENSIONS}
        className="hidden"
        onChange={(e) => {
          handleFiles(e.target.files, activeSlot);
          e.target.value = "";
        }}
      />

      {images.length > 0 && (
        <div className="flex items-center justify-between gap-2 text-[11px]">
          <span className="flex items-center gap-2 text-slate-400">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
            {images.length} file{images.length !== 1 ? "s" : ""} loaded
          </span>
          {currentMode.slots === 2 && emptySlots > 0 && (
            <span className="text-amber-400">
              {emptySlots} slot{emptySlots > 1 ? "s" : ""} empty
            </span>
          )}
        </div>
      )}
    </div>
  );
}
