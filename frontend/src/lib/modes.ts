import type { InputMode } from "../types/api";

export interface InputModeConfig {
  key: InputMode;
  label: string;
  slots: number;
  slotLabels: string[];
  description: string;
}

export const INPUT_MODES: InputModeConfig[] = [
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

export function getInputModeConfig(mode: InputMode): InputModeConfig {
  return INPUT_MODES.find((m) => m.key === mode)!;
}