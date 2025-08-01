// server/routes/scan.ts
import express from 'express';
import { supabase } from '../utils/supabaseClient';
import { fetchBingLinks, fetchSdsByName, scrapeProductInfo } from '../utils/scraper';
import { isValidCode } from '../utils/validation';
import logger from '../utils/logger';

const router = express.Router();

router.post('/', async (req, res) => {
  const { code } = req.body;
  if (!isValidCode(code)) return res.status(403).json({ error: 'Invalid barcode' });
  logger.info({ code }, '[SCAN] Searching for barcode');

  const { data: existing, error: fetchErr } = await supabase
    .from('product')
    .select('*')
    .eq('barcode', code)
    .maybeSingle();

  if (fetchErr) return res.status(500).json({ error: fetchErr.message });

  if (existing) {
    let updated = { ...existing };

    if (!existing.sds_url && existing.name) {
      const foundSds = await fetchSdsByName(existing.name);
      if (foundSds) {
        await supabase.from('product').update({ sds_url: foundSds }).eq('barcode', code);
        updated.sds_url = foundSds;
      }
    }

    return res.json({
      code,
      product: updated,
      scraped: [{
        url: '',
        name: updated.name || '',
        size: updated.contents_size_weight || '',
        sdsUrl: updated.sds_url || '',
      }],
      message: 'Item already in database',
    });
  }

  const urls = await fetchBingLinks(code);
  const scraped = (await Promise.all(urls.map(scrapeProductInfo))).filter(Boolean);
  const top = scraped[0] || { name: '', size: '', sdsUrl: '' };

  if (!top.sdsUrl) top.sdsUrl = await fetchSdsByName(top.name);

  const { data: found } = await supabase
    .from('product')
    .select('*')
    .eq('barcode', code)
    .maybeSingle();

  let data, error;
  if (found) {
    const update = await supabase
      .from('product')
      .update({
        name: top.name,
        contents_size_weight: top.size,
        sds_url: top.sdsUrl || null,
      })
      .eq('barcode', code)
      .select()
      .maybeSingle();
    data = update.data;
    error = update.error;
  } else {
    const insert = await supabase
      .from('product')
      .insert({
        barcode: code,
        name: top.name,
        contents_size_weight: top.size,
        sds_url: top.sdsUrl || null,
      })
      .select()
      .maybeSingle();
    data = insert.data;
    error = insert.error;
  }

  if (error) return res.status(500).json({ error: error.message });

  return res.json({ code, scraped, product: data });
});

export default router;
