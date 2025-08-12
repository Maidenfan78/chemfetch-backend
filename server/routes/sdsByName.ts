// server/routes/sdsByName.ts
import express from 'express';
import { searchSdsByName } from '../utils/scraper'; // Make sure this path is correct

const router = express.Router();

router.post('/', async (req, res) => {
  const { name } = req.body;
  if (!name) return res.status(400).json({ error: 'Missing name' });

  try {
    const url = await searchSdsByName(name);
    const verified = !!url;
    res.json({ sdsUrl: url, verified });
  } catch (err) {
    console.error("[/sds-by-name] Error:", err);
    res.status(500).json({ error: 'Failed to search SDS' });
  }
});

export default router;
