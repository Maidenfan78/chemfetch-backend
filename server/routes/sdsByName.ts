// server/routes/sdsByName.ts
import { Router } from "express";
import { z } from "zod";
import { searchSdsByName } from "../utils/scraper.js"; // ensure .js if ESM transpile

const router = Router();

const Body = z.object({
  name: z.string().min(2),
});

router.post("/", async (req, res) => {
  try {
    const { name } = Body.parse(req.body);
    const result = await searchSdsByName(name); // { url, verified } | null
    if (!result) {
      return res.status(404).json({ error: "SDS not found", name });
    }
    return res.json({ sdsUrl: result.url, verified: !!result.verified });
  } catch (err: any) {
    return res
      .status(400)
      .json({ error: err?.message ?? "Invalid request", details: err });
  }
});

export default router;
