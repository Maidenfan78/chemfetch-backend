// server/routes/confirm.ts
import express from 'express';
import { supabase } from '../utils/supabaseClient';
import { isValidCode, isValidName } from '../utils/validation';
import logger from '../utils/logger';
import { searchSdsByName } from '../utils/scraper';

const router = express.Router();

router.post('/', async (req, res) => {
  const { code, name = '', size = '' } = req.body;
  if (!isValidCode(code)) return res.status(403).json({ error: 'Invalid code' });
  if (name && !isValidName(name)) return res.status(403).json({ error: 'Invalid name' });
  logger.info({ code, name, size }, '[CONFIRM] Updating product');

  const updates = {
    name: name,
    contents_size_weight: size,
  };

  const { data, error } = await supabase
    .from('product')
    .update(updates)
    .eq('barcode', code)
    .select()
    .maybeSingle();

  if (error) return res.status(500).json({ error: error.message });

  let product = data as typeof data & { sds_url?: string };
  if (product && !product.sds_url && product.name) {
    try {
      const sds = await searchSdsByName(product.name);
      if (sds?.url) {
        await supabase.from('product').update({ sds_url: sds.url }).eq('barcode', code);
        product.sds_url = sds.url;
      }
    } catch (err: any) {
      logger.warn({ err: String(err) }, '[CONFIRM] SDS lookup failed');
    }
  }

  res.json({ success: true, product });
});

export default router;
