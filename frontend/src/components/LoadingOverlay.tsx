import { useState, useEffect } from "react";

interface Props {
  visible: boolean;
  message?: string;
}

const STEPS = [
  "Query Parsed",
  "Task Classified",
  "Model Selected",
  "Imagery Analyzed",
  "Evidence Generated",
  "Result Compiled",
];

const STATUS_MESSAGES = [
  "Scanning imagery...",
  "Classifying land cover...",
  "Running change detection...",
  "Processing spectral bands...",
  "Analyzing spatial features...",
  "Fusing optical and SAR data...",
  "Computing vegetation indices...",
  "Generating evidence references...",
];

function useStepProgress(visible: boolean) {
  const [prevVisible, setPrevVisible] = useState(visible);
  const [currentStep, setCurrentStep] = useState(0);
  const [completedSteps, setCompletedSteps] = useState<number[]>([]);

  if (prevVisible !== visible) {
    setPrevVisible(visible);
    if (!visible) {
      setCurrentStep(0);
      setCompletedSteps([]);
    }
  }

  useEffect(() => {
    if (!visible) return;

    const stepDuration = 300;
    const timer = setInterval(() => {
      setCurrentStep((prev) => {
        if (prev >= STEPS.length - 1) {
          clearInterval(timer);
          return prev;
        }
        setCompletedSteps((c) => [...c, prev]);
        return prev + 1;
      });
    }, stepDuration);

    return () => clearInterval(timer);
  }, [visible]);

  return { currentStep, completedSteps };
}

export default function LoadingOverlay({ visible, message }: Props) {
  const { currentStep, completedSteps } = useStepProgress(visible);

  if (!visible) return null;

  const displayMessage = message ?? STATUS_MESSAGES[currentStep % STATUS_MESSAGES.length];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 backdrop-blur-sm">
      <div className="panel w-96">
        <div className="panel-header">
          <span className="panel-label">Analysis in Progress</span>
          <div className="flex-1" />
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-teal-400" />
        </div>
        <div className="panel-body space-y-4">
          <div className="space-y-1">
            {STEPS.map((step, i) => {
              const isCompleted = completedSteps.includes(i);
              const isCurrent = i === currentStep;

              return (
                <div key={step} className="flex items-center gap-3 py-0.5">
                  <span className="flex w-5 flex-shrink-0 justify-center">
                    {isCompleted ? (
                      <svg width="15" height="15" viewBox="0 0 16 16" fill="none" className="text-emerald-400">
                        <path d="M3.5 8.5l3 3 6-6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    ) : (
                      <span
                        className={`block h-2 w-2 rounded-full transition-colors duration-200 ${
                          isCurrent ? "animate-pulse bg-teal-400" : "bg-slate-700"
                        }`}
                      />
                    )}
                  </span>
                  <span
                    className={`text-[12px] transition-colors duration-200 ${
                      isCompleted
                        ? "text-slate-300"
                        : isCurrent
                          ? "font-medium text-teal-400"
                          : "text-slate-600"
                    }`}
                  >
                    {step}
                  </span>
                </div>
              );
            })}
          </div>

          <div className="divider" />

          <div className="text-center">
            <p className="text-[13px] text-teal-400/80">{displayMessage}</p>
          </div>

          <div className="h-1 overflow-hidden rounded-full bg-slate-800">
            <div
              className="h-full rounded-full bg-teal-400/70 transition-all duration-300"
              style={{ width: `${((currentStep + 1) / STEPS.length) * 100}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}