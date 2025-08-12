// server/routes/sdsByName.ts
import express from 'express';
import { fetchSdsByName } from '../utils/scraper'; // Make sure this path is correct

const router = express.Router();

router.post('/', async (req, res) => {
  const { name, size } = req.body;
  if (!name) return res.status(400).json({ error: 'Missing name' });

  try {
    const { sdsUrl } = await fetchSdsByName(name, size);
    const verified = !!sdsUrl;
    res.json({ sdsUrl, verified });
  } catch (err) {
    console.error("[/sds-by-name] Error:", err);
    res.status(500).json({ error: 'Failed to search SDS' });
  }
});

export default router;
