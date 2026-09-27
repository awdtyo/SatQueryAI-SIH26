import { proxyGradio } from "../../../../proxyLib/gradioProxy";

export const config = {
  // Vercel Hobby plan ceiling (300+ needs Pro and fails deploy on Hobby).
  // SSE event stream for the queued job — stays open until complete/error.
  maxDuration: 60,
};

function eventIdFrom(req: any): string {
  const q = req.query?.eventId ?? req.query?.event_id;
  if (typeof q === "string" && q) return q;
  const urlPath = String(req.url || "").split("?")[0];
  const parts = urlPath.split("/").filter(Boolean);
  return parts.length > 0 ? parts[parts.length - 1] : "";
}

export default async function handler(req: any, res: any): Promise<void> {
  const eventId = eventIdFrom(req);
  if (!eventId) {
    res.status(404).json({ error: "Not found" });
    return;
  }
  await proxyGradio(req, res, ["call", "predict", eventId]);
}
