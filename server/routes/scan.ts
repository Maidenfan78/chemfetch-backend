import express from 'express';
import { supabase } from '../utils/supabaseClient';
import { searchItemByBarcode, searchSdsByName } from '../utils/scraper';
import { isValidCode } from '../utils/validation';
import logger from '../utils/logger';

const router = express.Router();

router.post('/', async (req, res) => {
  const { code } = req.body || {};
  if (!isValidCode(code)) return res.status(403).json({ error: 'Invalid barcode' });
  logger.info({ code }, '[SCAN] Searching for barcode');

  try {
    // 1) DB lookup first
    const { data: existing, error: fetchErr } = await supabase
      .from('product')
      .select('*')
      .eq('barcode', code)
      .maybeSingle();

    if (fetchErr) return res.status(500).json({ error: fetchErr.message });

    if (existing) {
      let updated = { ...existing } as typeof existing & { sds_url?: string };

      if (!existing.sds_url && existing.name) {
        try {
          const sds = await searchSdsByName(existing.name);
          if (sds?.url) {
            await supabase.from('product').update({ sds_url: sds.url }).eq('barcode', code);
            updated.sds_url = sds.url;
          }
        } catch (err: any) {
          logger.warn({ err: String(err) }, '[SCAN] SDS enrichment failed');
        }
      }

      return res.json({ code, product: updated, message: 'Item already in database' });
    }

    // 2) DB miss -> web search for name/size
    const webCandidate = await searchItemByBarcode(code);
    let sdsUrl: string | null = null;
    if (webCandidate?.name) {
      try {
        const sds = await searchSdsByName(webCandidate.name);
        if (sds?.url) sdsUrl = sds.url;
      } catch (err: any) {
        logger.warn({ err: String(err) }, '[SCAN] SDS search failed');
      }
    }

    const { data, error } = await supabase
      .from('product')
      .upsert({
        barcode: code,
        name: webCandidate?.name || null,
        contents_size_weight: webCandidate?.contents_size_weight || null,
        sds_url: sdsUrl,
      })
      .select()
      .maybeSingle();

    if (error) return res.status(500).json({ error: error.message });

    return res.json({ code, product: data, webCandidate });
  } catch (err: any) {
    logger.error({ code, err: String(err) }, '[SCAN] failed');
    return res.status(502).json({ error: 'SCAN_FAILED', message: String(err?.message || err) });
  }
});

export default router;
