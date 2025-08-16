// scripts/forceReprocessSds.ts
// Force reprocess ALL existing products with SDS URLs
import { createServiceRoleClient } from '../server/utils/supabaseClient.js';
import { triggerAutoSdsParsing } from '../server/utils/autoSdsParsing.js';

async function forceReprocessAllProducts() {
  try {
    console.log('🔥 FORCE REPROCESSING ALL PRODUCTS WITH SDS URLs');
    console.log('==================================================\n');
    
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
    console.log('🔄 Will reprocess ALL products (force=true)\n');

    console.log('🚀 Starting force reprocessing...');
    
    // Process products with delays to avoid overwhelming the system
    let processed = 0;
    let failed = 0;

    for (let i = 0; i < products.length; i++) {
      const product = products[i];
      const delay = i * 2000; // 2 second delay between each
      
      try {
        console.log(`📋 [${i + 1}/${products.length}] Force processing: ${product.name || product.barcode} (ID: ${product.id})`);
        
        const triggered = await triggerAutoSdsParsing(product.id, { 
          delay, 
          force: true  // Force reprocessing even if metadata exists
        });
        
        if (triggered) {
          processed++;
          console.log(`✅ Triggered force parsing for product ${product.id}`);
        } else {
          console.log(`⚠️  Failed to trigger parsing for product ${product.id}`);
          failed++;
        }
        
        // Small delay to avoid overwhelming logs
        await new Promise(resolve => setTimeout(resolve, 100));
        
      } catch (error) {
        failed++;
        console.error(`❌ Failed to process product ${product.id}:`, error);
      }
    }

    console.log(`\n📊 Force Processing Summary:`);
    console.log(`   • Triggered: ${processed}`);
    console.log(`   • Failed: ${failed}`);
    console.log(`   • Total: ${products.length}`);
    console.log(`\n⏳ SDS parsing is running in the background with FORCE=true.`);
    console.log(`📋 Check your backend server logs for detailed progress.`);
    console.log(`💡 Look for messages like "Auto-SDS: Successfully parsed and stored metadata"`);

  } catch (error) {
    console.error('💥 Script failed:', error);
    process.exit(1);
  }
}

// Run the script
if (process.argv[1].endsWith('forceReprocessSds.ts') || process.argv[1].endsWith('forceReprocessSds.js')) {
  forceReprocessAllProducts()
    .then(() => {
      console.log('\n✨ Force reprocessing script completed successfully');
      console.log('📈 Monitor your backend server logs to see the parsing progress.');
      process.exit(0);
    })
    .catch((error) => {
      console.error('\n💥 Script failed:', error);
      process.exit(1);
    });
}

export { forceReprocessAllProducts };
