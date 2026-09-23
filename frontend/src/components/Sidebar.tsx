import { useCallback, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import type { InputMode, UploadedImage } from "../types/api";
import { INPUT_MODES } from "../lib/modes";
import InputModeTabs from "./InputModeTabs";
import FileDropzone from "./FileDropzone";
import LoadedFileCard from "./LoadedFileCard";
import QueryLogAccordion from "./QueryLogAccordion";

const ACCEPTED_EXTENSIONS = ".tif,.tiff,.png,.jpg,.jpeg";

interface Props {
  images: UploadedImage[];
  setImages: Dispatch<SetStateAction<UploadedImage[]>>;
  inputMode: InputMode;
  setInputMode: (mode: InputMode) => void;
  queryHistory: string[];
  onReRunQuery: (query: string) => void;
}

export default function Sidebar({
  images,
  setImages,
  inputMode,
  setInputMode,
  queryHistory,
  onReRunQuery,
}: Props) {
  const [activeSlot, setActiveSlot] = useState(0);
  const [dragSlot, setDragSlot] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const currentMode = INPUT_MODES.find((m) => m.key === inputMode)!;

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
      setDragSlot(null);
    },
    [images, setImages, setInputMode],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent, slotIndex: number) => {
      e.preventDefault();
      setDragSlot(null);
      handleFiles(e.dataTransfer.files, slotIndex);
    },
    [handleFiles],
  );

  return (
    <div className="flex min-h-0 flex-col gap-3 lg:h-full lg:flex-shrink-0 lg:w-[300px]">
      <section className="rounded-xl border border-slate-800 bg-slate-900">
        <div className="panel-header">
          <span className="panel-label">Imagery Input</span>
        </div>
        <div className="space-y-4 p-4">
          <div>
            <label className="mb-2 block text-[11px] font-medium uppercase tracking-[0.1em] text-slate-400">
              Input Mode
            </label>
            <InputModeTabs value={inputMode} onChange={handleModeChange} />
            <p className="mt-2 text-[11px] leading-snug text-slate-500">{currentMode.description}</p>
          </div>

          <div className={currentMode.slots === 1 ? "space-y-2.5" : "grid grid-cols-2 gap-2.5"}>
            {currentMode.slotLabels.map((slotLabel, idx) => {
              const image = images[idx];
              if (image) {
                return (
                  <LoadedFileCard
                    key={`${inputMode}-${idx}`}
                    image={image}
                    roleLabel={slotLabel}
                    onRemove={() => removeImage(idx)}
                  />
                );
              }
              return (
                <FileDropzone
                  key={`${inputMode}-${idx}`}
                  label={slotLabel.toUpperCase()}
                  hint={currentMode.slots === 1 ? "Drop image or browse" : `Drop ${slotLabel} or browse`}
                  isDragActive={dragSlot === idx}
                  onBrowse={() => {
                    setActiveSlot(idx);
                    fileInputRef.current?.click();
                  }}
                  onDragActive={(active) => {
                    setActiveSlot(idx);
                    setDragSlot(active ? idx : null);
                  }}
                  onDrop={(e) => handleDrop(e, idx)}
                />
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

          {images.length > 0 && (
            <div className="flex items-center justify-between text-[11px]">
              <span className="text-slate-400">
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
      </section>

      {queryHistory.length > 0 && (
        <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-800 bg-slate-900">
          <div className="panel-header">
            <span className="panel-label">Query Log</span>
            <span className="ml-auto rounded border border-slate-700 bg-slate-800 px-1.5 py-0.5 text-[10px] font-medium tabular-nums text-slate-400">
              {queryHistory.length}
            </span>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-2.5">
            <QueryLogAccordion queries={queryHistory} onSelect={onReRunQuery} />
          </div>
        </section>
      )}
    </div>
  );
}