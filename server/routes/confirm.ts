// server/routes/confirm.ts
import express from 'express';
import { supabase } from '../utils/supabaseClient';
import { isValidCode, isValidName } from '../utils/validation';
import logger from '../utils/logger';

const router = express.Router();

router.post('/', async (req, res) => {
  const { code, name = '', size = '' } = req.body;
  if (!isValidCode(code)) return res.status(403).json({ error: 'Invalid code' });
  if (name && !isValidName(name)) return res.status(403).json({ error: 'Invalid name' });
  logger.info({ code, name, size }, '[CONFIRM] Updating product');

  const updates = {
    product_name: name,
    contents_size_weight: size,
  };

  const { data, error } = await supabase
    .from('products')
    .update(updates)
    .eq('barcode', code)
    .select()
    .maybeSingle();

  if (error) return res.status(500).json({ error: error.message });

  res.json({ success: true, product: data });
});

export default router;
