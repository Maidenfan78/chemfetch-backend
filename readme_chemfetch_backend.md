# 🚀 ChemFetch Backend

**Node.js + Express API server** with integrated Python OCR microservice for the ChemFetch chemical management platform.

This backend powers the mobile app (barcode scanning & OCR) and web client hub (chemical register management). It handles product discovery, web scraping, SDS parsing, and OCR processing through a combination of Node.js APIs and Python microservices.

---

## 🎯 Core Features

### API Endpoints

| Endpoint | Method | Purpose | Response Time |
|----------|--------|---------|---------------|
| `/scan` | POST | Barcode lookup with web scraping fallback | ~2-5 seconds |
| `/confirm` | POST | Save OCR-confirmed product data | ~200ms |
| `/sds-by-name` | POST | Find Safety Data Sheet URLs via intelligent search | ~3-8 seconds |
| `/parse-sds` | POST | Extract structured metadata from SDS PDFs | ~30-120 seconds |
| `/parse-sds/batch` | POST | Batch process multiple SDS documents | Variable |
| `/parse-sds/status/:id` | GET | Check SDS parsing status for a product | ~100ms |
| `/verify-sds` | POST | Validate SDS document relevance | ~30 seconds |
| `/ocr` | POST | Process images for text extraction | ~2-5 seconds |
| `/health` | GET | API health check | ~50ms |

### Key Capabilities
- **Australian-Focused Scraping**: Prioritizes `.com.au` domains and local retailers
- **Intelligent SDS Discovery**: Multiple search strategies including blob storage detection
- **Race Condition Protection**: Robust handling of long-running processes
- **Rate Limiting**: Prevents abuse with configurable limits
- **Timeout Management**: Graceful handling of slow external services
- **Structured Logging**: Comprehensive request/response logging with Pino

---

## 🛠️ Tech Stack

### Core Technologies
- **Node.js 18+** with TypeScript and ESM modules
- **Express 5** for HTTP server and routing
- **Puppeteer 24** for headless browser automation
- **Cheerio** for HTML parsing and scraping
- **Supabase Admin SDK** for database operations

### Python Microservice
- **Flask** web framework for OCR endpoints
- **PaddleOCR** for GPU-accelerated text recognition
- **pdfplumber + Tesseract** for PDF text extraction
- **OpenCV + PIL** for image preprocessing
- **requests** for PDF downloading and verification

### Security & Performance
- **express-rate-limit** with Redis support
- **helmet** for security headers
- **CORS** configuration for cross-origin requests
- **Zod** for request validation
- **Pino** for structured JSON logging
- **http-proxy-middleware** for OCR service proxying

---

## 📁 Project Structure

```
chemfetch-backend-claude/
├── server/                           # Node.js Express application
│   ├── index.ts                     # Application bootstrap & graceful shutdown
│   ├── app.ts                       # Express app configuration
│   ├── routes/                      # API route handlers
│   │   ├── scan.ts                  # Barcode scanning & product lookup
│   │   ├── confirm.ts               # Save confirmed product data
│   │   ├── sdsByName.ts             # SDS URL discovery
│   │   ├── parseSds.ts              # SDS metadata extraction
│   │   ├── verifySds.ts             # SDS document validation
│   │   ├── ocrProxy.ts              # OCR service proxy
│   │   └── health.ts                # Health check endpoint
│   └── utils/                       # Shared utilities
│       ├── scraper.ts               # Web scraping engine
│       ├── supabaseClient.ts        # Database client factory
│       ├── logger.ts                # Pino logger configuration
│       ├── cache.ts                 # Response caching utilities
│       ├── app.ts                   # Express app utilities
│       └── validation.ts            # Zod validation schemas
├── ocr_service/                     # Python OCR microservice
│   ├── ocr_service.py               # Flask server with OCR endpoints
│   ├── parse_sds.py                 # SDS PDF parsing engine
│   ├── test_parse_sds.py            # SDS parsing tests
│   ├── test_dependencies.py         # Dependency verification
│   ├── requirements.txt             # Python dependencies
│   ├── Dockerfile                   # Python service container
│   └── debug_images/                # OCR debugging output
├── docker-compose.yml               # Local development stack
├── Dockerfile                       # Multi-stage Node.js container
├── package.json                     # Node.js dependencies & scripts
├── tsconfig.json                    # TypeScript configuration
├── jest.config.js                   # Testing configuration
└── .env.example                     # Environment variable template
```

---

## ⚙️ Quick Start

### Prerequisites
- Node.js 18+ and npm
- Python 3.9+ and pip
- Supabase project with service role key

### 1. Environment Setup

Create `.env` file:
```env
# Server Configuration
PORT=3000
NODE_ENV=development

# Database
SB_URL=https://your-project.supabase.co
SB_SERVICE_KEY=your-service-role-key

# OCR Service
OCR_SERVICE_URL=http://localhost:5001

# Optional: External Services
REDIS_URL=redis://localhost:6379
```

### 2. Install Dependencies

```bash
# Node.js dependencies
npm install

# Python dependencies for OCR service
cd ocr_service
pip install -r requirements.txt
cd ..
```

### 3. Start Services

```bash
# Terminal 1: Start Python OCR service
cd ocr_service
python ocr_service.py
# Runs on http://localhost:5001

# Terminal 2: Start Node.js API server
npm start
# Runs on http://localhost:3000
```

### 4. Verify Setup

```bash
# Test API health
curl http://localhost:3000/health

# Test OCR service
curl http://localhost:5001/gpu-check

# Test end-to-end
curl -X POST http://localhost:3000/scan \
  -H "Content-Type: application/json" \
  -d '{"code": "044600069913"}'
```

---

## 🔍 API Documentation

### Barcode Scanning

**POST /scan**
```http
POST /scan
Content-Type: application/json

{
  "code": "044600069913"
}
```

**Response:**
```json
{
  "success": true,
  "product": {
    "id": 123,
    "barcode": "044600069913",
    "name": "Isocol Rubbing Alcohol",
    "manufacturer": "Reckitt Benckiser",
    "contents_size_weight": "75mL",
    "sds_url": "https://example.com/sds.pdf"
  },
  "source": "database"
}
```

### SDS Parsing

**POST /parse-sds**
```http
POST /parse-sds
Content-Type: application/json

{
  "product_id": 123,
  "sds_url": "https://example.com/sds.pdf",
  "force": false
}
```

**Response:**
```json
{
  "success": true,
  "product_id": 123,
  "message": "SDS parsed and stored successfully",
  "metadata": {
    "vendor": "Reckitt Benckiser",
    "issue_date": "2024-08-15",
    "hazardous_substance": true,
    "dangerous_good": false,
    "dangerous_goods_class": null,
    "packing_group": null,
    "subsidiary_risks": null
  }
}
```

### OCR Processing

**POST /ocr**
```http
POST /ocr
Content-Type: multipart/form-data

image: [binary file data]
left: 100          // optional crop coordinates
top: 100
width: 200
height: 150
screenWidth: 1080  // optional screen dimensions for scaling
screenHeight: 1920
```

**Response:**
```json
{
  "lines": [
    {
      "text": "Isocol Rubbing Alcohol",
      "confidence": 0.95,
      "box": [[10, 10], [200, 10], [200, 30], [10, 30]]
    }
  ],
  "text": "Isocol Rubbing Alcohol 75mL",
  "debug": {
    "tag": "20240815T123456_789012",
    "saved_images": true
  }
}
```

---

## 🐍 Python OCR Service

### Endpoints

| Endpoint | Purpose | GPU Accelerated |
|----------|---------|-----------------|
| `/ocr` | Extract text from images | ✅ |
| `/verify-sds` | Validate SDS document relevance | ❌ |
| `/parse-sds` | Extract structured SDS metadata | ❌ |
| `/gpu-check` | Check CUDA availability | - |

### Performance Optimization

**Image Preprocessing:**
- Automatic contrast enhancement with CLAHE
- Grayscale conversion for better OCR accuracy
- Smart resizing to optimal dimensions (max 4000px)

**PDF Processing:**
- Stream downloading with size limits (50MB max)
- Process only first 5 pages for verification
- Timeout protection (2 minutes per request)

**GPU Acceleration:**
- Automatic CUDA detection and usage
- Fallback to CPU if GPU unavailable
- Optimized batch processing for multiple images

---

## 🧪 Testing

### Unit Tests
```bash
npm test                    # Run all tests
npm test -- --watch        # Watch mode
npm test -- --coverage     # Coverage report
```

### OCR Service Tests
```bash
cd ocr_service
python -m pytest test_parse_sds.py -v
python test_dependencies.py  # Verify all dependencies
```

### Manual Testing
```bash
# Test barcode scanning
curl -X POST http://localhost:3000/scan \
  -H "Content-Type: application/json" \
  -d '{"code": "044600069913"}'

# Test SDS parsing
curl -X POST http://localhost:3000/parse-sds \
  -H "Content-Type: application/json" \
  -d '{"product_id": 123, "sds_url": "https://example.com/sds.pdf"}'
```

---

## 🚀 Deployment

### Docker Deployment

```yaml
# docker-compose.yml
version: '3.8'
services:
  backend:
    build: .
    ports:
      - "3000:3000"
      - "5001:5001"
    environment:
      - NODE_ENV=production
      - PORT=3000
      - OCR_SERVICE_URL=http://localhost:5001
    depends_on:
      - redis
      
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

### Cloud Deployment

**Railway/Render:**
- Build command: `npm install`
- Start command: `npm start`
- Set environment variables for production

**Fly.io (with GPU support):**
- Use GPU-enabled machines for OCR service
- Configure proper resource limits
- Set up health checks for both services

---

## 🔒 Security

### API Security
- **Rate Limiting**: Prevent abuse and DDoS attacks
- **Input Validation**: Zod schemas for all request bodies
- **CORS Configuration**: Restrict cross-origin requests
- **Helmet Integration**: Security headers and XSS protection
- **Service Role Authentication**: Secure database access

### Data Protection
- **Environment Variables**: Sensitive data in environment config
- **Database Isolation**: Row-level security for user data
- **Request Sanitization**: Clean and validate all inputs
- **Error Message Filtering**: Prevent information leakage

---

## 🐛 Troubleshooting

### Common Issues

**OCR Service Connection Errors:**
```bash
# Check if OCR service is running
curl http://localhost:5001/gpu-check

# Restart OCR service
cd ocr_service
python ocr_service.py
```

**Database Connection Issues:**
```bash
# Verify Supabase credentials
echo $SB_URL
echo $SB_SERVICE_KEY

# Test database connection
curl http://localhost:3000/health
```

**Memory Issues with Large PDFs:**
- Increase Node.js memory limit: `node --max-old-space-size=4096`
- Configure PDF size limits in `ocr_service/ocr_service.py`
- Monitor memory usage during SDS parsing

**Timeout Errors:**
- Adjust timeout values in route handlers
- Check network connectivity to external sites
- Verify scraping targets are accessible

### Debug Mode

Enable detailed logging:
```bash
export LOG_LEVEL=debug
export DEBUG_IMAGES=1
npm start
```

---

## 📊 Performance Tuning

### Node.js Optimization
- **Cluster Mode**: Use PM2 for multi-process deployment
- **Memory Management**: Configure heap size for large operations
- **Connection Pooling**: Optimize database connection usage
- **Caching Strategy**: Cache expensive scraping results

### Python OCR Optimization
- **GPU Utilization**: Ensure CUDA drivers are properly installed
- **Batch Processing**: Process multiple images simultaneously
- **Model Warming**: Pre-load OCR models on service start
- **Memory Cleanup**: Proper cleanup of large image arrays

---

## 🔄 Recent Updates

### Version 2024.12

**New Features:**
- ✅ SDS metadata parsing with vendor information
- ✅ Batch SDS processing capabilities
- ✅ Enhanced PDF verification with size limits
- ✅ Timeout protection for long-running operations
- ✅ Race condition fixes for concurrent requests

**Performance Improvements:**
- 🚀 SDS verification reduced from 6+ minutes to ~30 seconds
- 🚀 Stream processing for large PDF files
- 🚀 Smart caching for repeated scraping requests
- 🚀 Australian-focused search optimization

**Bug Fixes:**
- 🔧 Fixed "ERR_HTTP_HEADERS_SENT" race conditions
- 🔧 Improved client disconnect handling
- 🔧 Enhanced error messages for timeout scenarios
- 🔧 Better memory management for PDF processing

---

## 📚 API Rate Limits

| Endpoint | Rate Limit | Window | Notes |
|----------|------------|--------|-------|
| `/scan` | 60/hour | 1 hour | Per IP address |
| `/parse-sds` | 10/hour | 1 hour | Resource intensive |
| `/ocr` | 100/hour | 1 hour | Per IP address |
| `/verify-sds` | 30/hour | 1 hour | External requests |
| `/health` | Unlimited | - | Monitoring endpoint |

---

## 🤝 Contributing

### Development Workflow
1. Create feature branch from `main`
2. Implement changes with tests
3. Run full test suite: `npm test`
4. Update documentation if needed
5. Submit pull request with detailed description

### Code Standards
- **TypeScript**: Strict mode enabled
- **ESLint**: Follow configured rules
- **Prettier**: Auto-format on save
- **Testing**: Maintain >80% coverage
- **Documentation**: Update README for API changes

---

## 📄 License

This project is proprietary software. All rights reserved.

---

## 👥 Support

**Technical Issues:**
- Check troubleshooting section above
- Review logs for detailed error messages
- Test individual components in isolation

**Feature Requests:**
- Submit detailed requirements
- Include use cases and expected behavior
- Consider backward compatibility

**Performance Issues:**
- Enable debug logging
- Monitor resource usage
- Check external service dependencies

---

## 🗺️ Roadmap

### Q1 2025
- **Async Processing**: Queue-based SDS parsing
- **Advanced Caching**: Redis-based response caching
- **Metrics API**: Detailed performance and usage metrics
- **Webhook Support**: Real-time notifications for parsing completion

### Q2 2025
- **Multi-language OCR**: Support for non-English labels
- **Image Enhancement**: Advanced preprocessing for poor quality images
- **Batch Operations**: Bulk processing APIs
- **API Versioning**: Backward-compatible version management