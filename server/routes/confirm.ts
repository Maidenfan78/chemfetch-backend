// server/routes/confirm.ts
import express from 'express';
import { supabase } from '../utils/supabaseClient';
import { isValidCode, isValidName } from '../utils/validation';
import logger from '../utils/logger';
import { fetchSdsByName } from '../utils/scraper';

const router = express.Router();

router.post('/', async (req, res) => {
  const { code, name = '', size = '' } = req.body;
  if (!isValidCode(code)) return res.status(403).json({ error: 'Invalid code' });
  if (name && !isValidName(name)) return res.status(403).json({ error: 'Invalid name' });
  logger.info({ code, name, size }, '[CONFIRM] Upserting product');

  // Check for existing product to avoid duplicate entries when the user
  // repeatedly taps "Save & Find SDS". If the incoming payload matches the
  // current record, return 409 so the client can ignore the duplicate.
  const { data: existing, error: fetchErr } = await supabase
    .from('product')
    .select('barcode, name, contents_size_weight')
    .eq('barcode', code)
    .maybeSingle();

  if (fetchErr) return res.status(500).json({ error: fetchErr.message });

  if (existing && existing.name === name && existing.contents_size_weight === size) {
    return res.status(409).json({ error: 'Product already registered', product: existing });
  }

  const { data, error } = await supabase
    .from('product')
    .upsert({ barcode: code, name, contents_size_weight: size }, { onConflict: 'barcode' })
    .select()
    .maybeSingle();

  if (error) return res.status(500).json({ error: error.message });

  let product = data;

  if (product && !product.sds_url && product.name) {
    try {
      const { sdsUrl } = await fetchSdsByName(product.name, product.contents_size_weight || undefined);
      if (sdsUrl) {
        const update = await supabase
          .from('product')
          .update({ sds_url: sdsUrl })
          .eq('barcode', code)
          .select()
          .maybeSingle();
        if (!update.error) {
          product = update.data || { ...product, sds_url: sdsUrl };
        }
      }
    } catch (err: any) {
      logger.warn({ err: String(err) }, '[CONFIRM] SDS lookup failed');
    }
  }

  res.json({ success: true, product });
});

export default router;
