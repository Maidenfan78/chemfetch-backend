// server/routes/confirm.ts
import express from 'express';
import { supabase } from '../utils/supabaseClient';

const router = express.Router();

router.post('/', async (req, res) => {
  const { code, name = '', size = '' } = req.body;
  if (!code) return res.status(400).json({ error: 'Missing code' });

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
