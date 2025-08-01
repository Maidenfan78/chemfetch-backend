# 📦 ChemFetch Backend

This backend handles barcode lookups, product scraping, and SDS retrieval. A separate Python service performs OCR tasks.

---

## 🚀 Features

- `/scan` – Search barcode in Supabase or scrape details from Bing search results
- `/confirm` – Save confirmed product name and size
- `/sds-by-name` – Search for SDS PDF links using product name
- `/health` – API health & uptime check
- Rate limiting and input validation built in
- Structured logging with Pino

---

## 🛠 Tech Stack

- Node.js + TypeScript
- Express.js
- Pino for structured logging
- express-rate-limit for abuse protection
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
│   │   ├── confirm.ts
│   │   ├── health.ts
│   │   └── sdsByName.ts
│   ├── utils/                     # Helper modules
│   │   ├── scraper.ts
│   │   └── supabaseClient.ts
│   │   ├── logger.ts
│   │   └── validation.ts
├── ocr_service/
│   └── ocr_service.py             # Python OCR microservice
├── .env                           # Environment variables (not committed)
├── README.md                      # You are here
```

---

## ⚙️ Setup Instructions
ts
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
pip install -r requirements.txt
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

### 6. Run Tests
```bash
npm test
```

---

## 🔌 API Endpoints

### `POST /scan`
```json
{
  "code": "93549004"
}
```
Returns scraped and/or stored product info.


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
The backend exposes a simple health endpoint for uptime checks:
```
GET http://localhost:3000/health
```
The OCR microservice still provides a GPU status check at:
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
### The Schema
CREATE TABLE product (
  id SERIAL PRIMARY KEY,
  barcode TEXT NOT NULL,
  name TEXT,
  contents_size_weight TEXT,
  sds_url TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now()),
  CONSTRAINT unique_barcode UNIQUE (barcode)
);
user_chemical_watch_list
Tracks product usage per user (inventory, SDS status, risk info, etc.).

CREATE TABLE user_chemical_watch_list (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  product_id INTEGER REFERENCES product(id) ON DELETE CASCADE,
  quantity_on_hand INTEGER,
  location TEXT,
  sds_available BOOLEAN,
  sds_issue_date DATE,
  hazardous_substance BOOLEAN,
  dangerous_good BOOLEAN,
  dangerous_goods_class TEXT,
  description TEXT,
  packing_group TEXT,
  subsidiary_risks TEXT,
  consequence TEXT,
  likelihood TEXT,
  risk_rating TEXT,
  swp_required BOOLEAN,
  comments_swp TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now())
);
🔐 Row-Level Security (RLS)
RLS is enabled for user_chemical_watch_list to ensure users can only access their own chemical records.
---

## 🪪 License
Internal use only. Add license file if open sourced.

---

## 👷 Maintainer
Contact your internal team lead or platform owner for access, issues, or onboarding.
