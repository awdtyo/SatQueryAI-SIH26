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
  const [currentStep, setCurrentStep] = useState(0);
  const [completedSteps, setCompletedSteps] = useState<number[]>([]);

  useEffect(() => {
    if (!visible) {
      setCurrentStep(0);
      setCompletedSteps([]);
      return;
    }

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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-surface-900/70 backdrop-blur-sm">
      <div className="panel w-96">
        <div className="panel-header">
          <span className="panel-label">Analysis in Progress</span>
          <div className="flex-1" />
          <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
        </div>
        <div className="panel-body space-y-4">
          {/* Pipeline steps */}
          <div className="space-y-1">
            {STEPS.map((step, i) => {
              const isCompleted = completedSteps.includes(i);
              const isCurrent = i === currentStep;

              return (
                <div key={i} className="flex items-center gap-3 py-0.5">
                  <span className="w-5 flex-shrink-0 flex justify-center">
                    {isCompleted ? (
                      <svg width="15" height="15" viewBox="0 0 16 16" fill="none" className="text-signal-green">
                        <path d="M3.5 8.5l3 3 6-6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    ) : (
                      <span
                        className={`block w-2 h-2 rounded-full transition-colors duration-200 ${
                          isCurrent ? "bg-accent animate-pulse" : "bg-surface-400/40"
                        }`}
                      />
                    )}
                  </span>
                  <span
                    className={`text-[12px] transition-colors duration-200 ${
                      isCompleted
                        ? "text-ink-secondary"
                        : isCurrent
                          ? "text-accent font-medium"
                          : "text-ink-muted/50"
                    }`}
                  >
                    {step}
                  </span>
                </div>
              );
            })}
          </div>

          <div className="divider" />

          {/* Status message */}
          <div className="text-center">
            <p className="text-[13px] text-accent/80">{displayMessage}</p>
          </div>

          {/* Progress bar */}
          <div className="h-1 bg-surface-400/30 rounded-full overflow-hidden">
            <div
              className="h-full bg-accent/70 rounded-full transition-all duration-300"
              style={{ width: `${((currentStep + 1) / STEPS.length) * 100}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
