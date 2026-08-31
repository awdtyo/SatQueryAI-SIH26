import type { QueryRequest, QueryResponse } from "../types/api";

// TODO: Replace this entire module with real fetch calls once backend/api/ routes are finalized.
// The mock responses below are structured to match the schemas described in AGENTS.md
// (query text, image upload(s), ExecutionTrace with task, selected model/tool, parameters, confidence, evidence).

const MOCK_DELAY_MS = 1800;

const MOCK_RESPONSE: QueryResponse = {
  answer:
    "Analysis of the provided satellite imagery reveals significant land-cover change between the two acquisition dates. A newly developed impervious surface (likely construction) is visible in the northwest quadrant, covering approximately 2.3 hectares. Vegetation indices show a corresponding decline of 0.32 NDVI in the affected area. No cloud contamination was detected in either acquisition.",
  confidence: 0.87,
  execution_trace: {
    task: "change_detection",
    models_used: [
      {
        name: "SatVQA-v1",
        role: "visual_question_answering",
        parameters: { max_tokens: 256, temperature: 0.1 },
        latency_ms: 842,
      },
      {
        name: "ChangeFormer-B4",
        role: "change_detection",
        parameters: { threshold: 0.45, min_area_px: 64 },
        latency_ms: 1105,
      },
    ],
    parameters: {
      band_subset: "RGB+NIR",
      spatial_resolution_m: 10,
      radiometric_correction: "atmospheric",
      co_registration: "subpixel",
    },
    confidence: 0.87,
    evidence_refs: [
      {
        type: "bounding_box",
        description: "Detected change region — northwest quadrant",
        coordinates: [
          [120, 80],
          [310, 80],
          [310, 200],
          [120, 200],
        ],
        image_index: 1,
      },
      {
        type: "heatmap",
        description: "NDVI difference heatmap overlay",
        image_index: 1,
      },
    ],
    total_latency_ms: 1947,
  },
  evidence: [
    {
      type: "bounding_box",
      description: "Detected change region — northwest quadrant",
      coordinates: [
        [120, 80],
        [310, 80],
        [310, 200],
        [120, 200],
      ],
      image_index: 1,
    },
    {
      type: "heatmap",
      description: "NDVI difference heatmap overlay",
      image_index: 1,
    },
  ],
};

// TODO: Swap for real POST /api/query when backend is ready
export async function submitQuery(_request: QueryRequest): Promise<QueryResponse> {
  await new Promise((resolve) => setTimeout(resolve, MOCK_DELAY_MS));

  // TODO: Real implementation:
  // const formData = new FormData();
  // formData.append("query", request.query);
  // formData.append("input_mode", request.input_mode);
  // request.images.forEach((img, i) => formData.append(`image_${i}`, img));
  // const res = await fetch("/api/query", { method: "POST", body: formData });
  // if (!res.ok) throw new Error(`Query failed: ${res.status}`);
  // return res.json();

  return { ...MOCK_RESPONSE };
}

// TODO: Swap for real GET /api/health when backend is ready
export async function checkHealth(): Promise<{ status: string }> {
  await new Promise((resolve) => setTimeout(resolve, 200));
  // TODO: Real implementation:
  // const res = await fetch("/api/health");
  // return res.json();
  return { status: "mock" };
}
