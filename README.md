# 📦 ChemFetch Backend

This is the backend API for the ChemFetch platform. It provides barcode lookup, product scraping, OCR integration, and SDS (Safety Data Sheet) retrieval.

---

## 🚀 Features

- `/scan` – Search barcode in Supabase or scrape details from Bing search results
- `/ocr` – Process and crop image, relay to Python OCR microservice
- `/confirm` – Save confirmed product name and size
- `/sds-by-name` – Search for SDS PDF links using product name

---

## 🛠 Tech Stack

- Node.js + TypeScript
- Express.js
- Puppeteer + Cheerio (for scraping)
- Sharp (image preprocessing)
- Supabase Admin SDK
- Python OCR microservice (PaddleOCR)

---

## 📁 Folder Structure

```
chemfetch-backend/
├── server/
│   ├── index.ts                    # Express app entry point
│   ├── routes/                    # API route handlers
│   │   ├── scan.ts
│   │   ├── ocr.ts
│   │   ├── confirm.ts
│   │   └── sdsByName.ts
│   ├── utils/                     # Helper modules
│   │   ├── scraper.ts
│   │   └── supabaseClient.ts
├── ocr_service/
│   └── ocr_service.py             # Python OCR microservice
├── .env                           # Environment variables (not committed)
├── README.md                      # You are here
```

---

## ⚙️ Setup Instructions

### 1. Install Dependencies
```bash
cd server
npm install
```

### 2. Environment Variables
Create a `.env` file:
```env
SB_URL=https://yourproject.supabase.co
SB_SERVICE_KEY=your-service-role-key
```

### 3. Run Python OCR Microservice
```bash
cd ocr_service
python ocr_service.py
```

Make sure PaddleOCR is installed and working.

### 4. Start Backend API Server
```bash
cd server
npx tsx index.ts
```

### 5. Docker Deployment
Build and run both services using Docker Compose:
```bash
docker compose up --build
```
The backend will be available on `http://localhost:3000` and the OCR service on `http://localhost:5001`.

---

## 🔌 API Endpoints

### `POST /scan`
```json
{
  "code": "93549004"
}
```
Returns scraped and/or stored product info.

### `POST /ocr`
```json
{
  "image": "base64string",
  "cropInfo": { left, top, width, height, screenWidth, screenHeight, photoWidth, photoHeight }
}
```
Returns extracted text and structured OCR data.

### `POST /confirm`
```json
{
  "code": "93549004",
  "name": "Isocol Rubbing Alcohol",
  "size": "75ml"
}
```
Updates the existing product entry.

### `POST /sds-by-name`
```json
{
  "name": "WD-40 Multi-Use Product"
}
```
Returns a matching SDS PDF URL.

---

## 🧪 Health Check
You can check PaddleOCR GPU status with:
```
GET http://localhost:5001/gpu-check
```

---

## 📦 Deployment Targets
| Component       | Suggested Platform |
|----------------|--------------------|
| Backend API     | Railway / Render   |
| OCR Microservice| Fly.io / VPS       |
| Supabase        | supabase.io        |

---

## 🪪 License
Internal use only. Add license file if open sourced.

---

## 👷 Maintainer
Contact your internal team lead or platform owner for access, issues, or onboarding.
