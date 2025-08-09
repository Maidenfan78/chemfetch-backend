# ChemFetch – Updated Repo Overview & Backend README (workflow‑locked)

This document **locks in the end‑to‑end workflow** you described and updates both the **repo overview** and the **backend README** so you can copy/paste into the respective repos.

---

# 1) Repo Overview (update for AU‑biased, barcode→OCR→SDS flow)

## 🔗 Repository Map

| Repo Name                            | Purpose                                                                                                                               |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------- |
| **chemfetch-mobile**                 | Expo app that scans barcodes, captures OCR, shows the **Confirm** screen (Web vs OCR vs Manual) and then requests SDS by chosen name. |
| **chemfetch-client-hub**             | Next.js dashboard where customers see their chemical register and SDS links/metadata.                                                 |
| **chemfetch-admin-hub** *(optional)* | Internal control panel for jobs, logs, overrides.                                                                                     |
| **chemfetch-backend**                | Node + Express API. AU‑biased scraping; barcode lookup; OCR proxy; SDS search & verification; persistence to Supabase.                |
| **chemfetch-supabase**               | SQL schema, migrations, RLS, optional `sds_metadata` table for parsed facts.                                                          |

## 🇦🇺 Default Search Locale

All web lookups are **AU‑biased**. Scraper must apply: `mkt=en-AU`, `cc=AU`, `Accept-Language: en-AU,en;q=0.9` and (optionally) AU IP/geo bias where supported.

## 🔄 Locked Workflow (current MVP)

1. **Scan → DB check**

   * Mobile scans `barcode` and calls `POST /scan { code }`.
   * Backend checks `product` by `barcode`.
   * If found, return product immediately (no OCR).

2. **DB miss → Web search (AU) for product name by barcode**

   * Backend queries **`"Item {barcode}"`** (and may try variants like `"product {barcode}"`).
   * Scraper extracts **name** and **size/weight** from AU retailers/catalogues.
   * If this yields a plausible result, return it to the app as **Web candidate**.

3. **Parallel OCR fallback** *(to reduce lag)*

   * If a photo exists, OCR is kicked off in parallel via Python service.
   * App shows a **Confirm** screen with **3 panels**:

     * **Web** (data from step 2),
     * **OCR** (top lines + confidence),
     * **Manual** inputs (name + size).

4. **User chooses/enters final name (+ optional size)**

   * App submits selection to backend `POST /confirm { code, name, size? }` which upserts into `product`.

5. **SDS discovery by name (AU)**

   * Backend queries **`"{name} sds"`** (AU‑biased) and collects **PDF candidates**.
   * Each PDF is run through **/verify-sds** to ensure it contains:

     * the **product name** (string containment, tolerant to casing and common separators), and
     * any of **SDS / MSDS / Safety Data Sheet**.
   * First verified match becomes `product.sds_url`.

6. **Persistence**

   * On success: update `product` (`name`, `contents_size_weight`, `sds_url`).
   * Optional: enqueue SDS parsing job to populate `sds_metadata` (issue date, DG class, etc.).

## ⚡ Performance notes

* **Do simple HTTP + Cheerio first**; launch **Puppeteer** only when needed.
* **Parallelize** barcode web search and OCR.
* **Cache** `barcode → name` and `name → sds_url` (with short TTL for negatives).
* **Background SDS**: write product immediately and finish SDS lookup in a job; UI shows a pending badge.

---

# 2) chemfetch‑backend – README (updated, workflow‑locked)

## 📦 ChemFetch Backend

Backend API & headless scraper for the **ChemFetch** platform. Handles barcode lookups, AU‑biased scraping, OCR relaying, SDS discovery & verification, and persistence to Supabase.

### 🚀 Endpoints (MVP contract)

| Endpoint       | Method | Purpose                                                                                                                                                                                             |          |                                        |
| -------------- | ------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | -------------------------------------- |
| `/scan`        | POST   | **DB lookup by barcode**. On miss, run **AU‑biased web search** for `"Item {barcode}"` and return a **Web candidate** (name + size). May also trigger OCR in parallel (client‑side photo required). |          |                                        |
| `/confirm`     | POST   | Persist final **name/size** chosen by user (Web vs OCR vs Manual) after the Confirm screen. Upserts into `product` by `barcode`.                                                                    |          |                                        |
| `/sds-by-name` | POST   | AU‑biased search `"{name} sds"`; return first **verified** SDS PDF URL.                                                                                                                             |          |                                        |
| `/verify-sds`  | POST   | Download SDS PDF and verify **product name** + (**SDS**                                                                                                                                             | **MSDS** | **Safety Data Sheet**) appear in text. |
| `/ocr`         | POST   | Proxy image/crop to Python **PaddleOCR** service and return text/lines.                                                                                                                             |          |                                        |
| `/ocr/health`  | GET    | Quick health check for the OCR proxy.                                                                                                                                                               |          |                                        |
| `/health`      | GET    | API readiness probe.                                                                                                                                                                                |          |                                        |

> **AU bias:** All search helpers send `mkt=en-AU`, `cc=AU`, and `Accept-Language: en-AU,en;q=0.9`. Prefer AU domains when ranking.

### 🔎 Scraper rules

* **Barcode → Name:** query literally **`"Item {barcode}"`**; try `"product {barcode}"` as a fallback. Extract **name** and **size/weight** from first‑party/retailer pages.
* **Name → SDS:** query **`"{name} sds"`** and prefer **PDF** results. Only forward **PDF URLs** to `/verify-sds`.
* **Verification:** accept a PDF only if both checks pass:

  1. lower‑cased PDF text contains the **product name**; and
  2. the text contains **`sds`**, **`msds`**, or **`safety data sheet`**.

### 🔐 Data model (Supabase)

```sql
CREATE TABLE product (
  id SERIAL PRIMARY KEY,
  barcode TEXT NOT NULL UNIQUE,
  name TEXT,
  manufacturer TEXT,
  contents_size_weight TEXT,
  sds_url TEXT,
  created_at TIMESTAMPTZ DEFAULT timezone('utc', now())
);

-- Optional parsed snapshot (1:1 with product)
CREATE TABLE sds_metadata (
  product_id            INTEGER PRIMARY KEY REFERENCES product(id) ON DELETE CASCADE,
  issue_date            DATE,
  hazardous_substance   BOOLEAN,
  dangerous_good        BOOLEAN,
  dangerous_goods_class TEXT,
  description           TEXT,
  packing_group         TEXT,
  subsidiary_risks      TEXT,
  raw_json              JSONB,
  created_at            TIMESTAMPTZ DEFAULT timezone('utc', now())
);
```

### 🧩 Request examples

**1) /scan**

```jsonc
{ "code": "93549004" }
```

**Response (DB hit):**

```jsonc
{ "found": true, "product": {"id":1, "barcode":"93549004", "name":"Isocol Rubbing Alcohol", "contents_size_weight":"75 mL", "sds_url":"...pdf"} }
```

**Response (DB miss):**

```jsonc
{ "found": false, "webCandidate": {"name":"Isocol Rubbing Alcohol", "contents_size_weight":"75 mL"} }
```

**2) /confirm**

```jsonc
{ "code": "93549004", "name": "Isocol Rubbing Alcohol", "size": "75 mL" }
```

**3) /sds-by-name**

```jsonc
{ "name": "WD-40 Multi-Use Product" }
```

**Response:**

```jsonc
{ "sdsUrl": "https://.../WD40_SDS.pdf", "verified": true }
```

**4) /verify-sds**

```json
{ "url": "https://example.com/sds.pdf", "name": "Isocol Rubbing Alcohol" }
```

**Response:**

```json
{ "verified": true }
```

### ⚙️ Environment

```env
PORT=3000
SB_URL=https://<project>.supabase.co
SB_SERVICE_KEY=<service-role>
OCR_SERVICE_URL=http://127.0.0.1:5001
```

### 🛠️ Implementation checklist (backend)

* [ ] Add `searchAu(query)` helper to inject AU headers/params and domain boosting.
* [ ] Implement `searchItemByBarcode(barcode)` → returns `{ name, contents_size_weight }`.
* [ ] Implement `searchSdsByName(name)` → returns verified PDF URL via `/verify-sds`.
* [ ] In `/scan`, on DB miss, run `searchItemByBarcode` and **do not** block on OCR.
* [ ] In `/confirm`, upsert `product` and enqueue **SDS lookup** if `sds_url` is empty.
* [ ] Add caching for (barcode→name) and (name→sds) results.
* [ ] Graceful shutdown closes Puppeteer; prefer Cheerio first, Puppeteer as fallback.

### 📱 Confirm screen contract (mobile ↔ backend)

* The app must display **three visible choices** with data:

  1. **Web candidate** (from `/scan`),
  2. **OCR candidate** (from `/ocr`),
  3. **Manual** (inputs: name + size).
* On submit, call `/confirm`; then trigger `/sds-by-name` and update once verified.

### 🔧 Performance tips

* Start **web search & OCR in parallel** when practical.
* Use **range requests** or head checks before full PDF download when the verifier can still succeed; otherwise download once per candidate only.
* Negative‑cache failing domains/queries briefly to avoid thrash.

### 🐳 Local dev

```bash
python ocr_service/ocr_service.py   # 0.0.0.0:5001
node --loader tsx server/index.ts   # API on :3000
```

---

## Changelog (docs)

* 2025‑08‑09: Locked **AU‑biased** search; fixed query strings to `"Item {barcode}"` and `"{name} sds"`; clarified Confirm screen; defined SDS PDF verification rules; added performance & caching notes.
