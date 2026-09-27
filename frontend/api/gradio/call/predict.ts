import { proxyGradio } from "../../../../proxyLib/gradioProxy";

export const config = {
  // Vercel Hobby plan ceiling (300+ needs Pro and fails deploy on Hobby).
  // Warm queries take ~1-2s; a stone-cold first query may approach the limit
  // and cut off mid-stream — retrying lands warm.
  maxDuration: 60,
};

export default async function handler(req: any, res: any): Promise<void> {
  await proxyGradio(req, res, ["call", "predict"]);
}
