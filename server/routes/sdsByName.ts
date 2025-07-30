// server/routes/sdsByName.ts
import express from 'express';
import { fetchSdsByName } from '../utils/scraper';

const router = express.Router();

router.post('/', async (req, res) => {
  const { name } = req.body;
  if (!name) return res.status(400).json({ error: 'Missing name' });

  const sdsUrl = await fetchSdsByName(name);
  res.json({ sdsUrl });
});

export default router;