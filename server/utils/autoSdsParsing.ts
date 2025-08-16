// server/utils/autoSdsParsing.ts
import { createServiceRoleClient } from './supabaseClient';
import logger from './logger';
import { spawn } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

interface AutoParseOptions {
  force?: boolean;
  delay?: number; // Optional delay in milliseconds before parsing
}

/**
 * Automatically triggers SDS parsing for a product if it has an SDS URL
 * but no existing metadata (unless force=true)
 */
export async function triggerAutoSdsParsing(
  productId: number, 
  options: AutoParseOptions = {}
): Promise<boolean> {
  const { force = false, delay = 0 } = options;
  
  try {
    const supabase = createServiceRoleClient();
    
    // Get product info
    const { data: product, error: productError } = await supabase
      .from('product')
      .select('id, name, sds_url')
      .eq('id', productId)
      .single();

    if (productError || !product?.sds_url) {
      logger.debug(`Auto-SDS: No SDS URL for product ${productId}`);
      return false;
    }

    // Check if metadata already exists (unless force=true)
    if (!force) {
      const { data: existingMetadata } = await supabase
        .from('sds_metadata')
        .select('product_id')
        .eq('product_id', productId)
        .single();

      if (existingMetadata) {
        logger.debug(`Auto-SDS: Metadata already exists for product ${productId}`);
        return false;
      }
    }

    // Add optional delay (useful for rate limiting or batching)
    if (delay > 0) {
      setTimeout(() => executeSdsParsing(productId, product.sds_url), delay);
    } else {
      // Execute immediately in background
      setImmediate(() => executeSdsParsing(productId, product.sds_url));
    }

    logger.info(`Auto-SDS: Triggered parsing for product ${productId}`);
    return true;

  } catch (error) {
    logger.error(`Auto-SDS: Failed to trigger parsing for product ${productId}:`, error);
    return false;
  }
}

/**
 * Executes the actual SDS parsing in the background
 */
async function executeSdsParsing(productId: number, sdsUrl: string): Promise<void> {
  try {
    logger.info(`Auto-SDS: Starting background parsing for product ${productId}`);
    
    const scriptPath = path.join(__dirname, '../../ocr_service/parse_sds.py');
    const pythonProcess = spawn('python', [
      scriptPath,
      '--product-id', productId.toString(),
      '--url', sdsUrl
    ]);

    let stdout = '';
    let stderr = '';

    pythonProcess.stdout.on('data', (data) => {
      stdout += data.toString();
    });

    pythonProcess.stderr.on('data', (data) => {
      stderr += data.toString();
    });

    pythonProcess.on('close', async (code) => {
      if (code !== 0) {
        logger.error(`Auto-SDS: Python script failed for product ${productId} with exit code ${code}:`);
        logger.error(`Auto-SDS: stderr: ${stderr}`);
        logger.error(`Auto-SDS: stdout: ${stdout}`);
        return;
      }

      try {
        logger.debug(`Auto-SDS: Raw stdout for product ${productId}: ${stdout.trim()}`);
        const parsedMetadata = JSON.parse(stdout.trim());
        
        if (parsedMetadata.error) {
          logger.error(`Auto-SDS: Parse error for product ${productId}:`, parsedMetadata.error);
          return;
        }
        
        logger.debug(`Auto-SDS: Parsed metadata for product ${productId}:`, parsedMetadata);

        // Store metadata in database
        const supabase = createServiceRoleClient();
        const { error: upsertError } = await supabase
          .from('sds_metadata')
          .upsert({
            product_id: productId,
            vendor: parsedMetadata.vendor,
            issue_date: parsedMetadata.issue_date,
            hazardous_substance: parsedMetadata.hazardous_substance,
            dangerous_good: parsedMetadata.dangerous_good,
            dangerous_goods_class: parsedMetadata.dangerous_goods_class,
            description: parsedMetadata.product_name,
            packing_group: parsedMetadata.packing_group,
            subsidiary_risks: parsedMetadata.subsidiary_risks,
            raw_json: parsedMetadata,
          });

        if (upsertError) {
          logger.error(`Auto-SDS: Failed to store metadata for product ${productId}:`, upsertError);
          return;
        }

        // Update user watch lists
        await supabase
          .from('user_chemical_watch_list')
          .update({
            sds_available: true,
            sds_issue_date: parsedMetadata.issue_date,
            hazardous_substance: parsedMetadata.hazardous_substance,
            dangerous_good: parsedMetadata.dangerous_good,
            dangerous_goods_class: parsedMetadata.dangerous_goods_class,
            packing_group: parsedMetadata.packing_group,
            subsidiary_risks: parsedMetadata.subsidiary_risks,
          })
          .eq('product_id', productId);

        logger.info(`Auto-SDS: Successfully parsed and stored metadata for product ${productId}`);

      } catch (dbError) {
        logger.error(`Auto-SDS: Database error for product ${productId}:`, dbError);
      }
    });

    // Set timeout (3 minutes for background processing)
    setTimeout(() => {
      if (!pythonProcess.killed) {
        pythonProcess.kill();
        logger.warn(`Auto-SDS: Timeout parsing product ${productId}`);
      }
    }, 3 * 60 * 1000);

  } catch (error) {
    logger.error(`Auto-SDS: Execution error for product ${productId}:`, error);
  }
}

/**
 * Batch process all products with SDS URLs but no metadata
 */
export async function triggerBatchAutoSdsParsing(): Promise<void> {
  try {
    const supabase = createServiceRoleClient();
    
    // Get all products with SDS URLs that don't have metadata
    const { data: products } = await supabase
      .from('product')
      .select('id, name, sds_url')
      .not('sds_url', 'is', null)
      .not('sds_url', 'eq', '');

    if (!products?.length) {
      logger.info('Auto-SDS: No products found for batch processing');
      return;
    }

    // Get existing metadata to filter out already processed products
    const { data: existingMetadata } = await supabase
      .from('sds_metadata')
      .select('product_id');

    const existingIds = new Set(existingMetadata?.map(m => m.product_id) || []);
    const pendingProducts = products.filter(p => !existingIds.has(p.id));

    logger.info(`Auto-SDS: Starting batch processing for ${pendingProducts.length} products`);

    // Process with delays to avoid overwhelming the system
    for (let i = 0; i < pendingProducts.length; i++) {
      const product = pendingProducts[i];
      const delay = i * 5000; // 5 second delay between each
      
      await triggerAutoSdsParsing(product.id, { delay });
    }

  } catch (error) {
    logger.error('Auto-SDS: Batch processing failed:', error);
  }
}