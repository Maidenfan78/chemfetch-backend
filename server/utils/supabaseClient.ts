// server/utils/supabaseClient.ts
import { createClient } from '@supabase/supabase-js';
import dotenv from 'dotenv';

dotenv.config();

export const supabase = createClient(
  process.env.SB_URL || '',
  process.env.SB_SERVICE_KEY || ''
);
