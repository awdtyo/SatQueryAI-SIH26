import type { InputMode } from "../types/api";

/** One selectable imagery-input configuration. */
export interface InputModeOption {
  key: InputMode;
  label: string;
  slots: number;
  slotLabels: string[];
  description: string;
}

export const INPUT_MODES: InputModeOption[] = [
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

export const ACCEPTED_EXTENSIONS = ".tif,.tiff,.png,.jpg,.jpeg";

export const ACCEPTED_TAGS = ["GeoTIFF", "TIFF", "PNG", "JPEG"];

/** Never throws — falls back to the first (single) configuration. */
export function inputModeOption(mode: InputMode): InputModeOption {
  return INPUT_MODES.find((m) => m.key === mode) ?? INPUT_MODES[0]!;
}
