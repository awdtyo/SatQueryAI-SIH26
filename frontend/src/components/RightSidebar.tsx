import type { ExecutionTrace } from "../types/api";
import ExecutionTimeline from "./ExecutionTimeline";
import ConfidenceRing from "./ConfidenceRing";
import StatusPill from "./StatusPill";
import type { SystemStatus } from "./StatusPill";

interface Props {
  trace: ExecutionTrace | null;
  confidence: number | null;
}

const SERVICES: { label: string; status: SystemStatus }[] = [
  { label: "Controller", status: "online" },
  { label: "VQA Module", status: "online" },
  { label: "Change Detection", status: "online" },
  { label: "Grounding Engine", status: "online" },
  { label: "SAR Fusion", status: "standby" },
  { label: "GPU / T4", status: "online" },
];

export default function RightSidebar({ trace, confidence }: Props) {
  return (
    <div className="flex min-h-0 flex-col gap-3 lg:h-full lg:flex-shrink-0 lg:w-[320px]">
      <ExecutionTimeline trace={trace} />

      {confidence !== null && (
        <section className="panel flex-shrink-0 animate-slide-up">
          <div className="panel-header">
            <span className="panel-label">Confidence</span>
          </div>
          <div className="panel-body">
            <ConfidenceRing value={confidence} />
          </div>
        </section>
      )}

      <section className="panel flex min-h-0 flex-1 flex-col">
        <div className="panel-header">
          <span className="panel-label">System Status</span>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          <ul className="space-y-2">
            {SERVICES.map((svc) => (
              <li key={svc.label} className="flex items-center justify-between gap-2">
                <span className="text-[12px] text-slate-300">{svc.label}</span>
                <StatusPill status={svc.status} />
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
}