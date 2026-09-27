import { proxyGradio } from "../../../proxyLib/gradioProxy";

export const config = {
  // Vercel Hobby plan ceiling (300+ needs Pro and fails deploy on Hobby).
  maxDuration: 60,
};

export default async function handler(req: any, res: any): Promise<void> {
  await proxyGradio(req, res, ["info"]);
}
