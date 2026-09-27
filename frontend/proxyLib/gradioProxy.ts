/**
 * Shared Gradio → HF Space proxy logic (imported by the explicit route files
 * under frontend/api/gradio/). Kept OUTSIDE api/ so it never becomes a route.
 *
 * Browser → same-origin /api/gradio/* → Space /gradio_api/*, attaching
 * `Authorization: Bearer <HF_TOKEN>` server-side so ZeroGPU bills the
 * account's own quota instead of the anonymous pool (which 429s).
 */

const ALLOWED: Record<string, string[]> = {
  info: ["info"],
  upload: ["upload"],
};

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

export async function proxyGradio(req: any, res: any, segments: string[]): Promise<void> {
  const base = spaceBase();
  if (!base || !/^https:\/\//i.test(base)) {
    res.status(500).json({
      error:
        "Gradio proxy misconfigured: set SATQUERY_SPACE_URL " +
        "(https://<user>-satquery-backend.hf.space) in Vercel environment variables.",
    });
    return;
  }

  if (segments.length === 0) {
    res.status(404).json({ error: "Not found" });
    return;
  }

  const qs = req.url && req.url.includes("?") ? req.url.slice(req.url.indexOf("?")) : "";
  const upstreamUrl = `${base}/gradio_api/${segments.map(encodeURIComponent).join("/")}${qs}`;

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
  // NOTE: incoming authorization/cookie headers are deliberately NOT forwarded.

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
      body: body ?? undefined,
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

export { ALLOWED };
