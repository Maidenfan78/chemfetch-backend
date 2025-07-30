// server/routes/sdsByName.ts
import express from 'express';
import { fetchSdsByName } from '../utils/scraper';
import { isValidName } from '../utils/validation';
import logger from '../utils/logger';

const router = express.Router();

router.post('/', async (req, res) => {
  const { name } = req.body;
  if (!isValidName(name)) return res.status(403).json({ error: 'Invalid name' });

  logger.info({ name }, '[SDS] Fetching by name');
  const sdsUrl = await fetchSdsByName(name);
  res.json({ sdsUrl });
});

export default router;