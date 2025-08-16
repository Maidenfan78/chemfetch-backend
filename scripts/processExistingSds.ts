// scripts/processExistingSds.ts
// Run this script to process all existing products with SDS URLs
import { createServiceRoleClient } from '../server/utils/supabaseClient.js';
import { triggerAutoSdsParsing } from '../server/utils/autoSdsParsing.js';

async function processExistingProducts(force: boolean = false) {
  try {
    console.log('🔍 Finding products with SDS URLs that need processing...');
    
    const supabase = createServiceRoleClient();
    
    // Get all products with SDS URLs
    const { data: products, error: productError } = await supabase
      .from('product')
      .select('id, name, sds_url, barcode')
      .not('sds_url', 'is', null)
      .not('sds_url', 'eq', '');

    if (productError) {
      throw new Error(`Failed to fetch products: ${productError.message}`);
    }

    if (!products?.length) {
      console.log('✅ No products found with SDS URLs');
      return;
    }

    console.log(`📦 Found ${products.length} products with SDS URLs`);

    let pendingProducts = products;

    if (!force) {
      // Get existing metadata to filter out already processed
      const { data: existingMetadata, error: metadataError } = await supabase
        .from('sds_metadata')
        .select('product_id');

      if (metadataError) {
        console.warn(`⚠️  Could not fetch existing metadata: ${metadataError.message}`);
      }

      const existingIds = new Set(existingMetadata?.map(m => m.product_id) || []);
      pendingProducts = products.filter(p => !existingIds.has(p.id));

      console.log(`🔄 ${pendingProducts.length} products need SDS processing`);
      console.log(`✅ ${products.length - pendingProducts.length} products already processed`);

      if (pendingProducts.length === 0) {
        console.log('🎉 All products are already processed!');
        console.log('💡 Use --force to reprocess all products with updated parsing logic');
        return;
      }
    } else {
      console.log(`🔄 FORCE MODE: Reprocessing all ${products.length} products`);
    }

    console.log('🚀 Starting batch processing...');
    
    // Process products with delays to avoid overwhelming the system
    let processed = 0;
    let failed = 0;

    for (let i = 0; i < pendingProducts.length; i++) {
      const product = pendingProducts[i];
      const delay = i * 3000; // 3 second delay between each
      
      try {
        console.log(`📋 [${i + 1}/${pendingProducts.length}] Processing: ${product.name || product.barcode}`);
        
        const triggered = await triggerAutoSdsParsing(product.id, { delay, force });
        
        if (triggered) {
          processed++;
          console.log(`✅ Triggered parsing for product ${product.id}`);
        } else {
          console.log(`⚠️  Skipped product ${product.id} (may already have metadata and force=false)`);
        }
        
        // Small delay to avoid overwhelming logs
        await new Promise(resolve => setTimeout(resolve, 100));
        
      } catch (error) {
        failed++;
        console.error(`❌ Failed to process product ${product.id}:`, error);
      }
    }

    console.log(`\n📊 Processing Summary:`);
    console.log(`   • Triggered: ${processed}`);
    console.log(`   • Failed: ${failed}`);
    console.log(`   • Total: ${pendingProducts.length}`);
    console.log(`\n⏳ SDS parsing is running in the background. Check logs for progress.`);
    console.log(`📈 Use GET /parse-sds/status/:product_id to monitor individual products.`);

  } catch (error) {
    console.error('💥 Script failed:', error);
    process.exit(1);
  }
}

// CLI usage
if (process.argv[1].endsWith('processExistingSds.ts') || process.argv[1].endsWith('processExistingSds.js')) {
  console.log('🧪 ChemFetch SDS Processor');
  console.log('==========================\n');
  
  // Check for --force flag in all arguments
  const force = process.argv.some(arg => arg === '--force');
  
  if (force) {
    console.log('🔥 FORCE MODE ENABLED: Will reprocess all products\n');
  } else {
    console.log('📝 Normal mode: Will only process products without existing metadata\n');
  }
  
  processExistingProducts(force)
    .then(() => {
      console.log('\n✨ Script completed successfully');
      console.log('\n💡 Usage:');
      console.log('   npm run process-existing-sds        # Process only new products');
      console.log('   npm run process-existing-sds --force # Reprocess ALL products');
      process.exit(0);
    })
    .catch((error) => {
      console.error('\n💥 Script failed:', error);
      process.exit(1);
    });
}

export { processExistingProducts };