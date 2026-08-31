import { useState, useCallback } from "react";
import type { InputMode, QueryResponse, UploadedImage, AppError } from "./types/api";
import { submitQuery } from "./api/mockClient";
import Header from "./components/Header";
import ImageUploader from "./components/ImageUploader";
import ImageryViewer from "./components/ImageryViewer";
import QueryInput from "./components/QueryInput";
import ResultsPanel from "./components/ResultsPanel";
import ExecutionTracePanel from "./components/ExecutionTrace";
import ConfidenceGauge from "./components/ConfidenceGauge";
import LoadingOverlay from "./components/LoadingOverlay";

export default function App() {
  const [images, setImages] = useState<UploadedImage[]>([]);
  const [inputMode, setInputMode] = useState<InputMode>("single");
  const [isLoading, setIsLoading] = useState(false);
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [error, setError] = useState<AppError | null>(null);
  const [queryHistory, setQueryHistory] = useState<string[]>([]);

  const handleSubmit = useCallback(
    async (query: string) => {
      if (images.length === 0) {
        setError({ message: "Upload at least one image before querying." });
        return;
      }

      setError(null);
      setIsLoading(true);
      setResponse(null);

      try {
        const result = await submitQuery({
          query,
          input_mode: inputMode,
          images: images.map((img) => img.file),
        });
        setResponse(result);
        setQueryHistory((prev) => [query, ...prev].slice(0, 20));
      } catch (err) {
        setError({
          message: "Query processing failed",
          details: err instanceof Error ? err.message : String(err),
        });
      } finally {
        setIsLoading(false);
      }
    },
    [images, inputMode],
  );

  return (
    <div className="h-screen flex flex-col bg-surface-900 overflow-hidden">
      <Header />

      {/* Error banner — inline below header */}
      {error && (
        <div className="flex-shrink-0 mx-4 mt-2 px-4 py-2.5 border border-signal-red/25 bg-signal-red/5 flex items-center gap-3 animate-fade-in rounded-lg">
          <span className="text-signal-red text-xs font-semibold">!</span>
          <span className="text-[13px] text-ink">{error.message}</span>
          {error.details && (
            <span className="text-[11px] text-ink-muted ml-auto truncate max-w-xs">{error.details}</span>
          )}
          <button
            onClick={() => setError(null)}
            className="text-[11px] text-ink-muted hover:text-ink transition-colors ml-2"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Three-zone workspace */}
      <div className="flex-1 flex min-h-0 p-3 gap-3">
        {/* LEFT: Data Ingestion (~18-20%) */}
        <div className="w-[280px] flex-shrink-0 flex flex-col gap-3 min-h-0">
          <section className="panel flex-shrink-0">
            <div className="panel-header">
              <span className="panel-label">Imagery Input</span>
            </div>
            <div className="panel-body">
              <ImageUploader
                images={images}
                setImages={setImages}
                inputMode={inputMode}
                setInputMode={setInputMode}
              />
            </div>
          </section>

          {/* Query history — compact */}
          {queryHistory.length > 0 && (
            <section className="panel flex-1 min-h-0 flex flex-col">
              <div className="panel-header">
                <span className="panel-label">Query Log</span>
                <span className="tag-muted">{queryHistory.length}</span>
              </div>
              <div className="panel-body overflow-y-auto flex-1 min-h-0">
                <div className="space-y-1">
                  {queryHistory.map((q, i) => (
                    <button
                      key={i}
                      onClick={() => handleSubmit(q)}
                      className="w-full text-left text-[11px] text-ink-secondary px-2 py-1.5 hover:text-ink hover:bg-surface-700/40 transition-colors truncate rounded"
                    >
                      <span className="text-accent/40 mr-1.5">{">"}</span>
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            </section>
          )}
        </div>

        {/* CENTER: Imagery Viewer + Results (~55-60%) */}
        <div className="flex-1 flex flex-col gap-3 min-h-0 min-w-0">
          <ImageryViewer
            images={images}
            inputMode={inputMode}
            evidence={response?.evidence ?? []}
          />

          {/* Intelligence output below viewer */}
          {response && (
            <section className="panel flex-shrink-0 max-h-[38vh] overflow-y-auto animate-slide-up">
              <div className="panel-header">
                <span className="panel-label">Intelligence Result</span>
                <div className="flex-1" />
                <span className="text-[11px] font-medium text-signal-green/80">Received</span>
              </div>
              <div className="panel-body">
                <ResultsPanel response={response} />
              </div>
            </section>
          )}
        </div>

        {/* RIGHT: Analysis / Telemetry (~22-25%) */}
        <div className="w-[300px] flex-shrink-0 flex flex-col gap-3 min-h-0">
          <ExecutionTracePanel trace={response?.execution_trace ?? null} />

          {/* Confidence — always visible when response exists */}
          {response && (
            <section className="panel flex-shrink-0 animate-slide-up">
              <div className="panel-header">
                <span className="panel-label">Confidence</span>
              </div>
              <div className="panel-body">
                <ConfidenceGauge confidence={response.confidence} />
              </div>
            </section>
          )}

          {/* System status — compact + secondary */}
          <section className="panel flex-1 min-h-0 flex flex-col">
            <div className="panel-header">
              <span className="panel-label">System Status</span>
            </div>
            <div className="panel-body flex-1 overflow-y-auto">
              <div className="space-y-2.5">
                <StatusRow label="Controller" status="online" />
                <StatusRow label="VQA Module" status="online" />
                <StatusRow label="Change Detection" status="online" />
                <StatusRow label="Grounding Engine" status="online" />
                <StatusRow label="SAR Fusion" status="standby" />
                <StatusRow label="GPU / T4" status="online" />
              </div>
            </div>
          </section>
        </div>
      </div>

      {/* Bottom: Analysis Query Terminal */}
      <div className="flex-shrink-0 border-t border-surface-400/40 bg-surface-800/90 px-5 py-3.5">
        <QueryInput onSubmit={handleSubmit} disabled={isLoading} />
      </div>

      <LoadingOverlay visible={isLoading} />
    </div>
  );
}

/* ─── Inlined sub-components ─── */

function StatusRow({
  label,
  status,
  detail,
}: {
  label: string;
  status: "online" | "standby" | "error" | "mock";
  detail?: string;
}) {
  const colors = {
    online: "bg-signal-green",
    standby: "bg-signal-amber",
    error: "bg-signal-red",
    mock: "bg-ink-muted",
  };

  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <span className={`w-1.5 h-1.5 rounded-full ${colors[status]}`} />
        <span className="text-[12px] text-ink-secondary">{label}</span>
      </div>
      <div className="flex items-center gap-1.5">
        {detail && <span className="text-[10px] text-ink-muted">{detail}</span>}
        <span className={`text-[10px] uppercase ${status === "error" ? "text-signal-red" : "text-ink-muted"}`}>
          {status}
        </span>
      </div>
    </div>
  );
}
