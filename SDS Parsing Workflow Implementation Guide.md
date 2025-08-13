# SDS Parsing Workflow Implementation Guide

## 🎯 Overview

The SDS (Safety Data Sheet) parsing system is now complete and ready for implementation. This guide explains the workflow, triggers, and usage patterns for parsing SDS documents into structured metadata.

## 🏗️ Architecture

### Components Added:
1. **New API Endpoint**: `/parse-sds` in chemfetch-backend
2. **Database Migration**: Added `vendor` field to `sds_metadata` table
3. **Complete Python Parser**: `parse_sds.py` with OCR fallback capability

## 📝 API Endpoints

### 1. Parse Single SDS
```http
POST /parse-sds
Content-Type: application/json

{
  "product_id": 123,
  "sds_url": "https://example.com/sds.pdf",  // optional - uses product's sds_url if not provided
  "force": false                             // optional - re-parse even if metadata exists
}
```

**Response:**
```json
{
  "success": true,
  "product_id": 123,
  "message": "SDS parsed and stored successfully",
  "metadata": {
    "vendor": "Chemical Company Ltd",
    "issue_date": "2024-01-15",
    "hazardous_substance": true,
    "dangerous_good": true,
    "dangerous_goods_class": "3",
    "packing_group": "II",
    "subsidiary_risks": "6.1",
    "hazard_statements": ["H225", "H301", "H311"]
  }
}
```

### 2. Batch Parse Multiple SDS
```http
POST /parse-sds/batch
Content-Type: application/json

{
  "parse_all_pending": true,    // Parse all products with SDS URLs that lack metadata
  "force": false               // Re-parse existing metadata
}
```

**OR specify specific products:**
```json
{
  "product_ids": [123, 124, 125],
  "force": false
}
```

### 3. Check Parsing Status
```http
GET /parse-sds/status/123
```

**Response:**
```json
{
  "success": true,
  "product_id": 123,
  "has_metadata": true,
  "metadata": { ... }
}
```

## 🔄 When to Trigger SDS Parsing

### Automatic Triggers (Recommended Implementation):

1. **New Product with SDS URL Added**
   - Trigger: When `product.sds_url` is first populated
   - Location: In mobile app after SDS URL is found/confirmed
   - Implementation: Add webhook or direct API call after SDS URL confirmation

2. **SDS URL Updated**
   - Trigger: When existing `product.sds_url` changes
   - Action: Parse with `force: true` to update metadata

3. **Batch Processing Jobs**
   - Scheduled job (e.g., nightly) to process pending SDS documents
   - Call `/parse-sds/batch` with `parse_all_pending: true`
   - Good for catching any missed documents

### Manual Triggers:

1. **Client Hub Admin Interface**
   - Add "Parse SDS" button for individual products
   - Add "Parse All Pending" button for bulk processing

2. **API Integration**
   - External systems can trigger parsing via API
   - Useful for bulk imports or data migration

## 🛠️ Implementation Steps

### 1. Database Setup
```sql
-- Run the new migration
-- File: 20250814000001_add_vendor_to_sds_metadata.sql
ALTER TABLE public.sds_metadata ADD COLUMN vendor TEXT;
```

### 2. Update Database Types
```bash
cd chemfetch-supabase-claude
supabase gen types typescript --local > supabase/database.types.ts
```

### 3. Backend Integration
The new `/parse-sds` routes are already added to `server/app.ts`. Make sure to:
- Install any missing dependencies
- Ensure Python environment has required packages (see `ocr_service/requirements.txt`)
- Test the endpoint with a sample product

### 4. Frontend Integration Options

#### Option A: Add to Mobile App (Recommended)
```typescript
// After SDS URL is found/confirmed in mobile app
const triggerSdsParsing = async (productId: number, sdsUrl: string) => {
  try {
    const response = await fetch(`${API_BASE}/parse-sds`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        product_id: productId, 
        sds_url: sdsUrl 
      })
    });
    
    const result = await response.json();
    if (result.success) {
      console.log('SDS parsing initiated');
    }
  } catch (error) {
    console.error('Failed to trigger SDS parsing:', error);
  }
};
```

#### Option B: Add to Client Hub
```typescript
// In chemical watch list or product detail page
const parseSds = async (productId: number) => {
  setLoading(true);
  try {
    const response = await fetch(`/api/parse-sds`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        product_id: productId,
        force: true 
      })
    });
    
    const result = await response.json();
    if (result.success) {
      toast.success('SDS parsed successfully');
      // Refresh data
    }
  } catch (error) {
    toast.error('Failed to parse SDS');
  } finally {
    setLoading(false);
  }
};
```

## 🔍 Monitoring & Troubleshooting

### Key Log Locations:
- **Backend logs**: Check for Python script execution errors
- **Python logs**: Parsing script creates debug files in ocr_service directory
- **Database logs**: Monitor `sds_metadata` table insertions

### Common Issues:
1. **Python script fails**: Check requirements.txt dependencies
2. **PDF parsing fails**: Script includes OCR fallback for image-based PDFs
3. **Timeout errors**: Large PDFs may exceed 5-minute limit - consider increasing timeout

### Debug Files Created:
- `original_{product_id}.pdf` - Downloaded PDF
- `page_{page_num}_{product_id}.png` - Extracted page images (if OCR used)
- `ocr_text_{product_id}.txt` - Full OCR text output

## 📊 Performance Considerations

- **Single SDS parsing**: ~30 seconds to 5 minutes depending on PDF complexity
- **Batch processing**: Process sequentially with 1-second delays between requests
- **OCR fallback**: Adds significant processing time but handles image-based PDFs
- **Storage**: Debug files can accumulate - consider cleanup job

## 🎯 Success Metrics

Track these metrics to monitor system effectiveness:
- **Parse success rate**: `successful_parses / total_attempts`
- **Data extraction accuracy**: Manual spot-checks of parsed data
- **Processing time**: Average time per SDS document
- **Client hub usage**: How often users view/use parsed SDS metadata

## ✅ Next Steps

1. **Test the implementation**:
   - Test single product parsing
   - Test batch processing
   - Verify database updates

2. **Add UI components**:
   - Parse button in client hub
   - Status indicators for parsing progress
   - Display parsed metadata in watch list

3. **Set up automation**:
   - Add parsing triggers to mobile app workflow
   - Set up scheduled batch processing
   - Implement error notification system

4. **Monitor and optimize**:
   - Track success rates and processing times
   - Tune parsing patterns for better accuracy
   - Add more SDS document formats as needed