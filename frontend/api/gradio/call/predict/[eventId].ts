/**
 * Vercel serverless proxy: browser → same-origin /api/gradio/call/predict/{event_id}
 * (SSE stream) → Space /gradio_api/call/predict/{event_id}.
 *
 * Why this exists: called anonymously from a browser, ZeroGPU attributes jobs
 * to a shared anonymous-caller quota pool and calls fail with 429 from
 * device-api.zero/schedule. This proxy attaches `Authorization: Bearer
 * <HF_TOKEN>` server-side so usage is attributed to the owner's own quota.
 *
 * Security: HF_TOKEN lives ONLY in server-side env (Vercel Project →
 * Settings → Environment Variables). It is never part of the browser bundle.
 * Client-supplied Authorization/Cookie headers are deliberately NOT forwarded.
 *
 * NOTE: intentionally self-contained (no imports) — Vercel typechecks each
 * api/ file standalone, so shared modules outside api/ fail the build.
 */

export const config = {
  // Vercel Hobby plan ceiling (300+ needs Pro and fails deploy on Hobby).
  // SSE event stream for the queued job — stays open until complete/error.
  maxDuration: 60,
};

function eventIdFrom(req: any): string {
  const q = req.query?.eventId ?? req.query?.event_id;
  if (typeof q === "string" && q) return q;
  const urlPath: string = typeof req.url === "string" ? req.url.split("?")[0] ?? "" : "";
  const parts = urlPath.split("/").filter(Boolean);
  const last: string | undefined = parts[parts.length - 1];
  return typeof last === "string" ? last : "";
}

function spaceBase(): string {
  return (process.env.SATQUERY_SPACE_URL || "").replace(/\/$/, "");
}

function readRawBody(req: any): Promise<Buffer | null> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (c: Buffer) => chunks.push(Buffer.isBuffer(c) ? c : Buffer.from(c)));
    req.on("end", () => resolve(chunks.length > 0 ? Buffer.concat(chunks) : null));
    req.on("error", reject);
  });
}

export default async function handler(req: any, res: any): Promise<void> {
  const eventId = eventIdFrom(req);
  if (!eventId) {
    res.status(404).json({ error: "Not found" });
    return;
  }
  await proxyUpstream(req, res, `call/predict/${eventId.split("/").pop()}`);
}

async function proxyUpstream(req: any, res: any, suffix: string): Promise<void> {
  const base = spaceBase();
  if (!base || !/^https:\/\//i.test(base)) {
    res.status(500).json({
      error:
        "Gradio proxy misconfigured: set SATQUERY_SPACE_URL " +
        "(https://<user>-satquery-backend.hf.space) in Vercel environment variables.",
    });
    return;
  }

  const qs: string =
    typeof req.url === "string" && req.url.includes("?") ? req.url.slice(req.url.indexOf("?")) : "";
  const upstreamUrl = `${base}/gradio_api/${suffix}${qs}`;

  const headers: Record<string, string> = {};
  if (typeof req.headers?.["content-type"] === "string") {
    headers["content-type"] = req.headers["content-type"];
  }
  if (typeof req.headers?.accept === "string") {
    headers["accept"] = req.headers.accept;
  }
  // The whole point of this proxy: authenticate the Space call so ZeroGPU
  // bills the account's own quota instead of the anonymous pool.
  const hfToken = process.env.HF_TOKEN || "";
  if (hfToken) {
    headers["authorization"] = `Bearer ${hfToken}`;
  }

  let body: Buffer | null = null;
  if (req.method !== "GET" && req.method !== "HEAD") {
    try {
      body = await readRawBody(req);
    } catch {
      res.status(400).json({ error: "Failed to read request body" });
      return;
    }
    if (body) {
      headers["content-length"] = String(body.length);
    }
  }

  let upstream: Response;
  try {
    upstream = await fetch(upstreamUrl, {
      method: req.method,
      headers,
      // Uint8Array (not Buffer) to satisfy DOM fetch BodyInit types
      body: body ? new Uint8Array(body) : undefined,
    });
  } catch (err) {
    res.status(502).json({
      error: `Gradio proxy could not reach the Space: ${err instanceof Error ? err.message : String(err)}`,
    });
    return;
  }

  res.status(upstream.status);
  const contentType = upstream.headers.get("content-type");
  if (contentType) {
    res.setHeader("content-type", contentType);
  }
  res.setHeader("cache-control", "no-store");
  res.setHeader("x-accel-buffering", "no"); // don't let proxies buffer the SSE stream

  if (!upstream.body) {
    res.end();
    return;
  }
  try {
    const reader = upstream.body.getReader();
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      res.write(Buffer.from(value));
    }
  } catch {
    // Upstream stream broke mid-flight (e.g. ZeroGPU eviction) — end what we have;
    // the client surfaces "stream closed before completion" and can retry.
  } finally {
    res.end();
  }
}
