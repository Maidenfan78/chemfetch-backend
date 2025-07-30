// server/routes/scan.ts
import express from 'express';
import { supabase } from '../utils/supabaseClient';
import { fetchBingLinks, fetchSdsByName, scrapeProductInfo } from '../utils/scraper';
import { isValidCode } from '../utils/validation';

const router = express.Router();

router.post('/', async (req, res) => {
  const { code } = req.body;
  if (!isValidCode(code)) return res.status(403).json({ error: 'Invalid barcode' });
  console.log('[SCAN] Searching for barcode:', code);

  // Check if already in DB
  const { data: existing, error: fetchErr } = await supabase
    .from('products')
    .select('*')
    .eq('barcode', code)
    .maybeSingle();

  if (fetchErr) return res.status(500).json({ error: fetchErr.message });

  if (existing) {
    let updated = { ...existing };

    // Try to find SDS if missing
    if (!existing.sds_url && existing.product_name) {
      const foundSds = await fetchSdsByName(existing.product_name);
      if (foundSds) {
        await supabase.from('products').update({ sds_url: foundSds }).eq('barcode', code);
        updated.sds_url = foundSds;
      }
    }

    return res.json({
      code,
      product: updated,
      scraped: [{
        url: '',
        name: updated.product_name || '',
        size: updated.contents_size_weight || '',
        sdsUrl: updated.sds_url || '',
      }],
      message: 'Item already in database',
    });
  }

  // Fresh scrape
  const urls = await fetchBingLinks(code);
  const scraped = (await Promise.all(urls.map(scrapeProductInfo))).filter(Boolean);
  const top = scraped[0] || { name: '', size: '', sdsUrl: '' };

  if (!top.sdsUrl) top.sdsUrl = await fetchSdsByName(top.name);

  // Manual UPSERT
  const { data: found } = await supabase
    .from('products')
    .select('*')
    .eq('barcode', code)
    .maybeSingle();

  let data, error;
  if (found) {
    const update = await supabase
      .from('products')
      .update({
        product_name: top.name,
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
      .from('products')
      .insert({
        barcode: code,
        product_name: top.name,
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