import { useState, useCallback } from "react";
import type { InputMode, QueryResponse, UploadedImage, AppError } from "./types/api";
import { submitQuery } from "./api/mockClient";
import Header from "./components/Header";
import Sidebar from "./components/Sidebar";
import ImageryViewer from "./components/ImageryViewer";
import ResultOverlay from "./components/ResultOverlay";
import RightSidebar from "./components/RightSidebar";
import QueryBar from "./components/QueryBar";
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
    <div className="flex h-screen flex-col bg-slate-950 overflow-hidden">
      <Header />

      {error && (
        <div className="mx-4 mt-2 flex flex-shrink-0 animate-fade-in items-center gap-3 rounded-lg border border-rose-500/25 bg-rose-500/5 px-4 py-2.5">
          <span className="text-xs font-semibold text-rose-400">!</span>
          <span className="text-[13px] text-slate-200">{error.message}</span>
          {error.details && (
            <span className="ml-auto max-w-xs truncate text-[11px] text-slate-500">{error.details}</span>
          )}
          <button
            type="button"
            onClick={() => setError(null)}
            className="ml-2 text-[11px] text-slate-500 transition-colors hover:text-slate-200"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Three-column workspace */}
      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-3 lg:flex-row lg:overflow-hidden">
        {/* LEFT: Imagery input + query log */}
        <Sidebar
          images={images}
          setImages={setImages}
          inputMode={inputMode}
          setInputMode={setInputMode}
          queryHistory={queryHistory}
          onReRunQuery={handleSubmit}
        />

        {/* CENTER: Satellite viewport + floating results */}
        <div className="relative min-h-[55vh] min-w-0 flex-1 lg:min-h-0">
          <ImageryViewer images={images} inputMode={inputMode} evidence={response?.evidence ?? []} />
          {response && <ResultOverlay response={response} onClose={() => setResponse(null)} />}
        </div>

        {/* RIGHT: Execution trace + confidence + system status */}
        <RightSidebar trace={response?.execution_trace ?? null} confidence={response?.confidence ?? null} />
      </div>

      {/* Bottom: analysis query bar */}
      <div className="flex-shrink-0 border-t border-slate-800 bg-slate-900 px-5 py-3.5">
        <QueryBar onSubmit={handleSubmit} disabled={isLoading} />
      </div>

      <LoadingOverlay visible={isLoading} />
    </div>
  );
}