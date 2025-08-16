// server/routes/batchSds.ts
import express from 'express';
import { createServiceRoleClient } from '../utils/supabaseClient';
import { triggerAutoSdsParsing, triggerBatchAutoSdsParsing } from '../utils/autoSdsParsing';
import logger from '../utils/logger';

const router = express.Router();

/**
 * POST /batch-sds/process-all
 * Process all products with SDS URLs that don't have metadata yet
 */
router.post('/process-all', async (req, res) => {
  try {
    logger.info('[BATCH-SDS] Starting batch processing of all pending products');
    
    // Trigger batch processing (runs in background)
    triggerBatchAutoSdsParsing();
    
    res.json({
      success: true,
      message: 'Batch SDS processing started in background',
    });
  } catch (error) {
    logger.error('[BATCH-SDS] Batch processing failed:', error);
    res.status(500).json({
      success: false,
      message: 'Failed to start batch processing',
      error: (error as Error).message,
    });
  }
});

/**
 * POST /batch-sds/process-product
 * Process a specific product by ID
 * Body: { product_id: number, force?: boolean }
 */
router.post('/process-product', async (req, res) => {
  const { product_id, force = false } = req.body;
  
  if (!product_id || typeof product_id !== 'number') {
    return res.status(400).json({
      success: false,
      message: 'product_id is required and must be a number',
    });
  }

  try {
    logger.info({ productId: product_id, force }, '[BATCH-SDS] Processing specific product');
    
    const triggered = await triggerAutoSdsParsing(product_id, { force });
    
    if (triggered) {
      res.json({
        success: true,
        message: `SDS parsing triggered for product ${product_id}`,
        product_id,
      });
    } else {
      res.json({
        success: false,
        message: `No SDS parsing needed for product ${product_id} (no SDS URL or metadata already exists)`,
        product_id,
      });
    }
  } catch (error) {
    logger.error(`[BATCH-SDS] Failed to process product ${product_id}:`, error);
    res.status(500).json({
      success: false,
      message: `Failed to process product ${product_id}`,
      error: (error as Error).message,
    });
  }
});

/**
 * GET /batch-sds/status
 * Get statistics about SDS processing status
 */
router.get('/status', async (req, res) => {
  try {
    const supabase = createServiceRoleClient();
    
    // Get total products with SDS URLs
    const { count: totalWithSds } = await supabase
      .from('product')
      .select('*', { count: 'exact', head: true })
      .not('sds_url', 'is', null)
      .not('sds_url', 'eq', '');
    
    // Get products with existing metadata
    const { count: totalWithMetadata } = await supabase
      .from('sds_metadata')
      .select('*', { count: 'exact', head: true });
    
    // Get products needing processing
    const { data: productsWithSds } = await supabase
      .from('product')
      .select('id')
      .not('sds_url', 'is', null)
      .not('sds_url', 'eq', '');
    
    const { data: productsWithMetadata } = await supabase
      .from('sds_metadata')
      .select('product_id');
    
    const processedIds = new Set(productsWithMetadata?.map(m => m.product_id) || []);
    const pendingCount = (productsWithSds || []).filter(p => !processedIds.has(p.id)).length;
    
    res.json({
      success: true,
      statistics: {
        total_products_with_sds: totalWithSds || 0,
        total_with_metadata: totalWithMetadata || 0,
        pending_processing: pendingCount,
        processing_rate: totalWithSds ? Math.round(((totalWithMetadata || 0) / totalWithSds) * 100) : 0,
      },
    });
  } catch (error) {
    logger.error('[BATCH-SDS] Failed to get status:', error);
    res.status(500).json({
      success: false,
      message: 'Failed to get processing status',
      error: (error as Error).message,
    });
  }
});

export default router;