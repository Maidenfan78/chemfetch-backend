# 📦 ChemFetch Backend

*Backend API & headless scraper for the ****ChemFetch**** platform*

This service powers **chemfetch‑mobile** (barcode & OCR capture) and **chemfetch‑client‑hub** (web dashboard).  It handles barcode look‑ups, product scraping, OCR relaying, and SDS discovery, then persists everything to Supabase.

---

## 🚀 Core Features

| Endpoint       | Method   | Purpose                                                                                                        |
| -------------- | -------- | -------------------------------------------------------------------------------------------------------------- |
| `/scan`        | **POST** | Look up a barcode in Supabase → fall back to web‑scrape if not found                                           |
| `/confirm`     | **POST** | Persist the name / size chosen by the user after OCR review                                                    |
| `/sds-by-name` | **POST** | Given a product name, crawl the web for a matching **PDF** SDS link                                            |
| `/ocr`         | **POST** | **NEW** – Proxy image/crop details to the Python PaddleOCR micro‑service and stream the result back to the app |
| `/health`      | **GET**  | Lightweight readiness / uptime probe                                                                           |

Additional behaviour:

- **Rate‑limiting & Zod input validation** on every mutating route.
- **Graceful shutdown** – SIGINT / SIGTERM closes Puppeteer before exit.
- Structured JSON logging with **Pino**.
- Transparent caching: successful scrapes are stored to avoid repeated external queries.

---

## 🛠️ Tech Stack

- **Node.js 18** + **TypeScript** (ESM)
- **Express 5**
- **tsx** runtime for zero‑build local dev (`npx tsx server/index.ts`)
- **Puppeteer** (headless Chromium) & **Cheerio** (HTML parsing)
- **Supabase Admin SDK** for DB writes
- **express‑rate‑limit** & **helmet** for basic hardening
- **Zod** for schema validation
- **Python micro‑service** (Flask + PaddleOCR) – separate container / process

---

## 📁 Project Structure

```
chemfetch-backend/
├── server/
│   ├── index.ts              # Express bootstrap + graceful shutdown
│   ├── routes/
│   │   ├── scan.ts
│   │   ├── confirm.ts
│   │   ├── sdsByName.ts
│   │   ├── ocr.ts            # <-- NEW proxy route
│   │   └── health.ts
│   ├── utils/
│   │   ├── scraper.ts        # Bing → first‑party site scraping
│   │   ├── supabaseClient.ts # Service‑role client factory
│   │   ├── logger.ts
│   │   ├── browser.ts        # Puppeteer singleton & cleanup helper
│   │   └── validation.ts     # Zod schemas shared by routes
├── ocr_service/
│   └── ocr_service.py        # PaddleOCR + Flask (GPU optional)
├── Dockerfile                # Multi‑stage build for Node & Python
├── docker-compose.yml        # Local stack orchestration
├── requirements.txt          # Python deps (for OCR service)
├── .env.example              # Sample env vars
└── README-chemfetch-backend.md (this file)
```

---

## ⚙️ Local Setup

### 1. Clone & Install

```bash
# Node deps
npm install            # from repo root (installs into ./server)

# Python deps (OCR service)
pip install -r requirements.txt  # or use a venv/conda
```

### 2. Environment Variables

Create a `.env` file at the repo root *or* export vars in your shell:

```env
# General
PORT=3000                   # API port (default 3000)
NODE_ENV=development

# Supabase (service‑role key required for write access)
SB_URL=https://<project>.supabase.co
SB_SERVICE_KEY=<service‑role_key>

# OCR micro‑service location (container, VM or LAN IP)
OCR_API_URL=http://127.0.0.1:5001
```

> The mobile app reads **EXPO\_PUBLIC\_BACKEND\_API\_URL**; keep that separately in the mobile `.env`.

### 3. Run the OCR micro‑service

```bash
python ocr_service/ocr_service.py  # listens on 0.0.0.0:5001
```

GPU is used automatically if PaddlePaddle‑GPU is installed and CUDA is available.

### 4. Start the API server

```bash
# plain node (good for prod images)
node --loader tsx server/index.ts

# or with Nodemon for hot reload
nodemon --watch server --exec "tsx server/index.ts"
```

The API will now be live on `http://localhost:3000`.

### 5. Docker (optional)

A single‑command local stack:

```bash
docker compose up --build
```

This spins up **backend‑api** (Node) + **ocr‑svc** (Python) networks.

### 6. Tests

```bash
npm run test   # Vitest + Supertest (coming soon)
```

---

## 🔌 Example Requests

### `POST /scan`

```jsonc
{
  "code": "93549004"
}
```

Response → `{ "barcode": "93549004", "name": "Isocol Rubbing Alcohol", ... }`

### `POST /ocr`

`multipart/form-data` with one or more `image` files plus optional crop params (`left`,`top`,`width`,`height`). Returns recognised lines + full text.

### `POST /confirm`

```jsonc
{
  "code": "93549004",
  "name": "Isocol Rubbing Alcohol",
  "size": "75 mL"
}
```

### `POST /sds-by-name`

```jsonc
{ "name": "WD‑40 Multi‑Use Product" }
```

Returns `{ "sdsUrl": "https://.../WD40_MSDS.pdf" }`.

---

## 🗄️ Database Schema (Supabase)

```sql
-- product master table
CREATE TABLE product (
  id SERIAL PRIMARY KEY,
  barcode TEXT NOT NULL UNIQUE,
  name TEXT,
  manufacturer TEXT,
  contents_size_weight TEXT,
  sds_url TEXT,
  created_at TIMESTAMPTZ DEFAULT timezone('utc', now())
);

-- per‑user inventory & risk info
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
  created_at TIMESTAMPTZ DEFAULT timezone('utc', now())
);

-- Enable RLS on user_chemical_watch_list so users can only see their own rows
ALTER TABLE user_chemical_watch_list ENABLE ROW LEVEL SECURITY;
```

---

## 📦 Deployment Matrix

| Component          | Recommended Host                        |
| ------------------ | --------------------------------------- |
| Backend API (Node) | Railway, Render, or Fly.io              |
| OCR service (Py)   | Fly.io / GPU VPS / Azure Container Apps |
| Supabase DB        | Supabase Cloud                          |

---

## 🪪 License & Contributing

This repository is currently **private / internal**.  Add a LICENSE file and contribution guidelines before open‑sourcing.

---

## 👷 Maintainers

For access, issues, or onboarding, ping **@Sav** on Slack or open a ticket in the internal Jira project `CHEM`.  Cheers!

