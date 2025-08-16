// server/routes/parseSds.ts
import { Router } from 'express';
import { spawn } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';
import logger from '../utils/logger';
import { createServiceRoleClient } from '../utils/supabaseClient';

// Get __dirname equivalent for ES modules
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const router = Router();

interface ParseSdsRequest {
  product_id: number;
  sds_url?: string;
  force?: boolean; // Force re-parse even if metadata exists
}

interface ParseSdsResponse {
  success: boolean;
  product_id: number;
  message: string;
  metadata?: any;
  error?: string;
}

/**
 * POST /parse-sds
 * Triggers SDS parsing for a specific product
 * Body: { product_id: number, sds_url?: string, force?: boolean }
 */
router.post('/', async (req, res) => {
  const { product_id, sds_url, force = false }: ParseSdsRequest = req.body;

  if (!product_id || typeof product_id !== 'number') {
    return res.status(400).json({
      success: false,
      message: 'product_id is required and must be a number',
    });
  }

  const supabase = createServiceRoleClient();

  try {
    // 1. Get product info from database
    const { data: product, error: productError } = await supabase
      .from('product')
      .select('id, name, sds_url, barcode')
      .eq('id', product_id)
      .single();

    if (productError) {
      logger.error('Failed to fetch product:', productError);
      return res.status(404).json({
        success: false,
        message: 'Product not found',
        error: productError.message,
      });
    }

    // 2. Use provided sds_url or fallback to product's sds_url
    const targetSdsUrl = sds_url || product.sds_url;
    
    if (!targetSdsUrl) {
      return res.status(400).json({
        success: false,
        message: 'No SDS URL available for this product',
      });
    }

    // 3. Check if metadata already exists (unless force=true)
    if (!force) {
      const { data: existingMetadata, error: metadataError } = await supabase
        .from('sds_metadata')
        .select('product_id, created_at')
        .eq('product_id', product_id)
        .single();

      if (existingMetadata && !metadataError) {
        return res.status(200).json({
          success: false,
          product_id,
          message: 'SDS metadata already exists. Use force=true to re-parse.',
        });
      }
    }

    // 4. Execute Python parsing script
    const scriptPath = path.join(__dirname, '../../ocr_service/parse_sds.py');
    logger.info(`Starting Python script: python ${scriptPath} --product-id ${product_id} --url ${targetSdsUrl}`);
    const pythonProcess = spawn('python', [
      scriptPath,
      '--product-id', product_id.toString(),
      '--url', targetSdsUrl
    ]);

    let stdout = '';
    let stderr = '';
    let responseHandled = false; // Flag to prevent multiple responses

    // Helper function to safely send response
    const sendResponse = (statusCode: number, data: any) => {
      if (!responseHandled && !res.headersSent) {
        responseHandled = true;
        return res.status(statusCode).json(data);
      } else {
        logger.warn(`Attempted to send response after headers sent or response handled for product ${product_id}`);
      }
    };

    pythonProcess.stdout.on('data', (data) => {
      stdout += data.toString();
    });

    pythonProcess.stderr.on('data', (data) => {
      stderr += data.toString();
    });

    pythonProcess.on('close', async (code) => {
      if (responseHandled) {
        logger.info(`Python script finished but response already handled for product ${product_id}`);
        return;
      }

      logger.info(`Python script finished with code ${code}`);
      logger.info(`Python stdout:`, stdout);
      logger.info(`Python stderr:`, stderr);
      
      if (code !== 0) {
        logger.error(`Python script failed with code ${code}:`, stderr);
        return sendResponse(500, {
          success: false,
          product_id,
          message: 'Failed to parse SDS',
          error: stderr || 'Python script execution failed',
        });
      }

      try {
        // 5. Parse the output from Python script
        const output = stdout.trim();
        let parsedMetadata;
        
        try {
          parsedMetadata = JSON.parse(output);
          
          // Check if Python script returned an error
          if (parsedMetadata.error) {
            logger.error('Python script returned error:', parsedMetadata.error);
            return sendResponse(500, {
              success: false,
              product_id,
              message: 'Failed to parse SDS',
              error: parsedMetadata.error,
            });
          }
        } catch (parseError) {
          logger.error('Failed to parse Python output as JSON:', output);
          return sendResponse(500, {
            success: false,
            product_id,
            message: 'Failed to parse SDS metadata',
            error: 'Invalid JSON output from parser',
          });
        }

        // 6. Store metadata in database
        logger.info(`Storing SDS metadata for product ${product_id}:`, parsedMetadata);
        
        const { error: upsertError } = await supabase
          .from('sds_metadata')
          .upsert({
            product_id,
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
          logger.error('Failed to store SDS metadata:', upsertError);
          return sendResponse(500, {
            success: false,
            product_id,
            message: 'Failed to store SDS metadata',
            error: upsertError.message,
          });
        }

        // 7. Update user watch lists with parsed data
        const { error: updateError } = await supabase
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
          .eq('product_id', product_id);

        if (updateError) {
          logger.warn('Failed to update user watch lists:', updateError);
          // Don't fail the request, just log the warning
        }

        logger.info(`Successfully parsed SDS for product ${product_id}`);
        return sendResponse(200, {
          success: true,
          product_id,
          message: 'SDS parsed and stored successfully',
          metadata: parsedMetadata,
        });

      } catch (dbError) {
        logger.error('Database error during SDS parsing:', dbError);
        return sendResponse(500, {
          success: false,
          product_id,
          message: 'Database error during SDS processing',
          error: (dbError as Error).message,
        });
      }
    });

    // Handle client disconnect
    req.on('close', () => {
      if (!responseHandled) {
        logger.info(`Client disconnected for product ${product_id}, killing Python process`);
        responseHandled = true;
        if (!pythonProcess.killed) {
          pythonProcess.kill();
        }
      }
    });

    // Set timeout for Python script execution (5 minutes)
    const timeoutId = setTimeout(() => {
      if (!responseHandled && !pythonProcess.killed) {
        pythonProcess.kill();
        logger.error(`Python script timeout for product ${product_id}`);
        sendResponse(504, {
          success: false,
          product_id,
          message: 'SDS parsing timeout',
          error: 'Script execution exceeded 5 minute limit',
        });
      }
    }, 5 * 60 * 1000);

    // Clear timeout if process completes normally
    pythonProcess.on('close', () => {
      clearTimeout(timeoutId);
    });

  } catch (error) {
    logger.error('Error in SDS parsing route:', error);
    return res.status(500).json({
      success: false,
      product_id,
      message: 'Internal server error',
      error: (error as Error).message,
    });
  }
});

/**
 * POST /parse-sds/batch
 * Triggers SDS parsing for multiple products with SDS URLs
 * Body: { product_ids?: number[], parse_all_pending?: boolean, force?: boolean }
 */
router.post('/batch', async (req, res) => {
  const { product_ids, parse_all_pending = false, force = false } = req.body;

  if (!product_ids && !parse_all_pending) {
    return res.status(400).json({
      success: false,
      message: 'Either product_ids array or parse_all_pending=true is required',
    });
  }

  const supabase = createServiceRoleClient();
  const results: any[] = [];

  try {
    let targetProducts: any[] = [];

    if (parse_all_pending) {
      // Get all products with SDS URLs that don't have metadata yet
      const { data: products, error } = await supabase
        .from('product')
        .select('id, name, sds_url, barcode')
        .not('sds_url', 'is', null)
        .not('sds_url', 'eq', '');

      if (error) {
        return res.status(500).json({
          success: false,
          message: 'Failed to fetch products',
          error: error.message,
        });
      }

      // Filter out products that already have metadata (unless force=true)
      if (!force) {
        const { data: existingMetadata } = await supabase
          .from('sds_metadata')
          .select('product_id');

        const existingIds = new Set(existingMetadata?.map(m => m.product_id) || []);
        targetProducts = products?.filter(p => !existingIds.has(p.id)) || [];
      } else {
        targetProducts = products || [];
      }
    } else {
      // Get specific products
      const { data: products, error } = await supabase
        .from('product')
        .select('id, name, sds_url, barcode')
        .in('id', product_ids);

      if (error) {
        return res.status(500).json({
          success: false,
          message: 'Failed to fetch products',
          error: error.message,
        });
      }

      targetProducts = products || [];
    }

    logger.info(`Starting batch SDS parsing for ${targetProducts.length} products`);

    // Process products sequentially to avoid overwhelming the system
    for (const product of targetProducts) {
      if (!product.sds_url) {
        results.push({
          product_id: product.id,
          success: false,
          message: 'No SDS URL available',
        });
        continue;
      }

      try {
        // Simulate the parsing request internally
        const parseRequest = new Promise<any>((resolve) => {
          const scriptPath = path.join(__dirname, '../../ocr_service/parse_sds.py');
          const pythonProcess = spawn('python', [
            scriptPath,
            '--product-id', product.id.toString(),
            '--url', product.sds_url
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
              resolve({
                product_id: product.id,
                success: false,
                message: 'Failed to parse SDS',
                error: stderr,
              });
              return;
            }

            try {
              const parsedMetadata = JSON.parse(stdout.trim());

              // Store in database
              await supabase
                .from('sds_metadata')
                .upsert({
                  product_id: product.id,
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

              // Update watch lists
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
                .eq('product_id', product.id);

              resolve({
                product_id: product.id,
                success: true,
                message: 'SDS parsed successfully',
                metadata: parsedMetadata,
              });

            } catch (error) {
              resolve({
                product_id: product.id,
                success: false,
                message: 'Failed to process SDS data',
                error: (error as Error).message,
              });
            }
          });

          // Timeout after 5 minutes
          setTimeout(() => {
            if (!pythonProcess.killed) {
              pythonProcess.kill();
              resolve({
                product_id: product.id,
                success: false,
                message: 'SDS parsing timeout',
              });
            }
          }, 5 * 60 * 1000);
        });

        const result = await parseRequest;
        results.push(result);
        
        // Small delay between requests to avoid overwhelming the system
        await new Promise(resolve => setTimeout(resolve, 1000));

      } catch (error) {
        results.push({
          product_id: product.id,
          success: false,
          message: 'Processing error',
          error: (error as Error).message,
        });
      }
    }

    const successCount = results.filter(r => r.success).length;
    logger.info(`Batch SDS parsing completed: ${successCount}/${results.length} successful`);

    return res.status(200).json({
      success: true,
      message: `Batch parsing completed: ${successCount}/${results.length} successful`,
      results,
    });

  } catch (error) {
    logger.error('Error in batch SDS parsing:', error);
    return res.status(500).json({
      success: false,
      message: 'Batch processing failed',
      error: (error as Error).message,
    });
  }
});

/**
 * GET /parse-sds/status/:product_id
 * Check SDS parsing status for a product
 */
router.get('/status/:product_id', async (req, res) => {
  const product_id = parseInt(req.params.product_id);

  if (isNaN(product_id)) {
    return res.status(400).json({
      success: false,
      message: 'Invalid product_id',
    });
  }

  const supabase = createServiceRoleClient();

  try {
    const { data: metadata, error } = await supabase
      .from('sds_metadata')
      .select('*')
      .eq('product_id', product_id)
      .single();

    if (error && error.code !== 'PGRST116') { // PGRST116 = row not found
      return res.status(500).json({
        success: false,
        message: 'Database error',
        error: error.message,
      });
    }

    return res.status(200).json({
      success: true,
      product_id,
      has_metadata: !!metadata,
      metadata: metadata || null,
    });

  } catch (error) {
    return res.status(500).json({
      success: false,
      message: 'Internal server error',
      error: (error as Error).message,
    });
  }
});

export default router;