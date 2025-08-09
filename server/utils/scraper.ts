/*
  scraper.ts — AU‑biased search helpers and SDS logic
  ---------------------------------------------------
  Exports:
    - searchAu(query)
    - searchItemByBarcode(barcode)
    - searchSdsByName(name)

  Dependencies (install if missing):
    npm i axios cheerio undici
*/

import axios, { AxiosRequestConfig } from "axios";
import * as cheerio from "cheerio";
import { setTimeout as delay } from "timers/promises";

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36";

const OCR_SERVICE_URL = process.env.OCR_SERVICE_URL || "http://127.0.0.1:5001"; // for /verify-sds

// ------------------------------------------------------------
// Shared helpers
// ------------------------------------------------------------

function auHeaders(): Record<string, string> {
  return {
    "User-Agent": UA,
    "Accept-Language": "en-AU,en;q=0.9",
    "Cache-Control": "no-cache",
  };
}

function withAuParams(url: string): string {
  const u = new URL(url);
  if (!u.searchParams.has("mkt")) u.searchParams.set("mkt", "en-AU");
  if (!u.searchParams.has("cc")) u.searchParams.set("cc", "AU");
  // Bing respects these; some engines just ignore.
  return u.toString();
}

async function fetchHtml(url: string, cfg: AxiosRequestConfig = {}) {
  const res = await axios.get<string>(withAuParams(url), {
    ...cfg,
    headers: { ...(cfg.headers || {}), ...auHeaders() },
    timeout: 12_000,
    validateStatus: (s) => s >= 200 && s < 400,
  });
  return res.data as string;
}

function absolute(href: string, base: string): string {
  try {
    return new URL(href, base).toString();
  } catch {
    return href;
  }
}

function looksLikePdf(u: string): boolean {
  return /\.pdf(\?|#|$)/i.test(u);
}

async function headIsPdf(u: string): Promise<boolean> {
  try {
    const res = await axios.head(u, {
      headers: auHeaders(),
      timeout: 8_000,
      maxRedirects: 3,
      validateStatus: (s) => s >= 200 && s < 400,
    });
    const ctype = (res.headers["content-type"] || "").toString();
    return /application\/pdf/i.test(ctype) || looksLikePdf(u);
  } catch {
    return looksLikePdf(u);
  }
}

// ------------------------------------------------------------
// 1) searchAu(query): Bing → DuckDuckGo fallback
// ------------------------------------------------------------

export async function searchAu(query: string): Promise<Array<{ title: string; url: string }>> {
  const results: Array<{ title: string; url: string }> = [];

  // Primary: Bing HTML
  try {
    const q = encodeURIComponent(query);
    const html = await fetchHtml(`https://www.bing.com/search?q=${q}&mkt=en-AU&cc=AU`);
    const $ = cheerio.load(html);
    $("li.b_algo h2 a, .b_algo h2 a").each((_, el) => {
      const title = $(el).text().trim();
      let href = $(el).attr("href") || "";
      if (href) {
        href = normalizeBingCk(href);
        results.push({ title, url: href });
      }
    });
  } catch (err) {
    // ignore, fallback will handle
  }

  if (results.length > 0) return dedupe(results);

  // Secondary: DuckDuckGo HTML
  try {
    const q = encodeURIComponent(query);
    const html = await fetchHtml(`https://html.duckduckgo.com/html/?q=${q}&kl=au-en`);
    const $ = cheerio.load(html);
    $("a.result__a").each((_, el) => {
      const title = $(el).text().trim();
      let href = $(el).attr("href") || "";
      if (href) {
        href = normalizeBingCk(href);
        results.push({ title, url: href });
      }
    });
  } catch (err) {
    // swallow
  }

  return dedupe(results);
}

function dedupe(items: Array<{ title: string; url: string }>) {
  const seen = new Set<string>();
  return items.filter((r) => {
    const key = r.url.replace(/[#?].*$/, "");
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

// ------------------------------------------------------------
// 2) searchItemByBarcode(barcode): "Item {barcode}" (+ variant)
// ------------------------------------------------------------

type ItemCandidate = { name?: string; contents_size_weight?: string; url?: string };

export async function searchItemByBarcode(barcode: string): Promise<ItemCandidate | null> {
  const queries = [
    `Item ${barcode}`,
    `product ${barcode}`,
  ];

  for (const q of queries) {
    const hits = await searchAu(q);
    for (const hit of hits.slice(0, 8)) {
      // Prefer AU retailers/domains by light heuristic
      if (!/\.au\b/i.test(hit.url) && /amazon|aliexpress|ebay/i.test(hit.url)) continue;
      try {
        const html = await fetchHtml(hit.url);
        const $ = cheerio.load(html);
        const cand = extractNameAndSize($, hit.url);
        if (cand.name) return { ...cand, url: hit.url };
      } catch {
        // try next
      }
      await delay(250);
    }
  }

  return null;
}

function extractNameAndSize($: cheerio.CheerioAPI, pageUrl: string): ItemCandidate {
  const texts: string[] = [];

  // Common sources
  const h1 = $("h1").first().text().trim();
  if (h1) texts.push(h1);
  const ogTitle = $('meta[property="og:title"]').attr("content")?.trim();
  if (ogTitle) texts.push(ogTitle);
  const title = $("title").text().trim();
  if (title) texts.push(title);

  // Retailer labels often near price/info
  $(".product-title, .ProductName, .prod-title, .productName, .pdp-title").each((_, el) => {
    const t = $(el).text().trim();
    if (t) texts.push(t);
  });

  const joined = texts.join(" \u2022 ");
  const name = cleanProductName(joined);
  const size = extractSize(joined);

  return { name, contents_size_weight: size };
}

function cleanProductName(s: string | undefined): string | undefined {
  if (!s) return undefined;
  // Remove shop suffixes and noise
  s = s.replace(/\s*\|\s*Buy.*$/i, "");
  s = s.replace(/\s*-\s*Bunnings.*$/i, "");
  s = s.replace(/\s*-\s*Officeworks.*$/i, "");
  s = s.replace(/\s*–\s*Woolworths.*$/i, "");
  // Trim any trailing SKU codes in brackets
  s = s.replace(/\s*\([^)]+\)\s*$/, "");
  return s.trim();
}

function normalizeBingCk(url: string): string {
  try {
    const u = new URL(url);
    // Bing “ck/a” uses the real target in the `u` param
    if (u.hostname === "www.bing.com" && u.pathname.startsWith("/ck/")) {
      const real = u.searchParams.get("u");
      if (real) return decodeURIComponent(real);
    }
  } catch { }
  return url;
}

function extractSize(s: string | undefined): string | undefined {
  if (!s) return undefined;
  const m = s.match(/\b(\d+(?:\.\d+)?)\s?(mL|L|g|kg|KG|G|ML|Litre|Litres)\b/i);
  return m ? `${m[1]} ${m[2]}`.replace(/\b(ml|g|kg)\b/i, (x) => x.toLowerCase()) : undefined;
}

// ------------------------------------------------------------
// 3) searchSdsByName(name): "<name> sds" → PDFs → /verify-sds
// ------------------------------------------------------------

export type VerifiedSds = { url: string; verified: boolean };

export async function searchSdsByName(name: string): Promise<VerifiedSds | null> {
  const query = `${name} sds`;
  const hits = await searchAu(query);

  // Prefer PDF candidates only
  const pdfFirst = hits.filter((h) => looksLikePdf(h.url));
  const maybePdf = hits.filter((h) => !looksLikePdf(h.url));

  const candidates: string[] = [];
  for (const h of pdfFirst) candidates.push(h.url);

  // Probe non-PDF links to see if they point/redirect to PDFs
  for (const h of maybePdf.slice(0, 10)) {
    if (await headIsPdf(h.url)) candidates.push(h.url);
  }

  // Lightweight domain preference for AU or manufacturers
  const rank = (u: string) => {
    let score = 0;
    if (/\.au\b/i.test(u)) score += 2;
    if (/sds|msds|safety[- ]?data[- ]?sheet/i.test(u)) score += 1;
    if (/\.pdf(\?|#|$)/i.test(u)) score += 1;
    return score;
  };
  candidates.sort((a, b) => rank(b) - rank(a));

  for (const url of candidates.slice(0, 8)) {
    const verified = await verifySds(url, name);
    if (verified) return { url, verified: true };
    await delay(200);
  }

  return null;
}

async function verifySds(url: string, name: string): Promise<boolean> {
  try {
    const res = await axios.post(
      `${OCR_SERVICE_URL.replace(/\/$/, "")}/verify-sds`,
      { url, name },
      { headers: { "Content-Type": "application/json", ...auHeaders() }, timeout: 15_000 }
    );
    return !!res.data?.verified;
  } catch (err) {
    return false;
  }
}

// ------------------------------------------------------------
// Convenience: composable function to find product
// ------------------------------------------------------------

export async function findProductByBarcode(barcode: string) {
  const cand = await searchItemByBarcode(barcode);
  if (!cand) return null;
  const sds = cand.name ? await searchSdsByName(cand.name) : null;
  return { ...cand, sdsUrl: sds?.url, sdsVerified: sds?.verified ?? false };
}


// ------------------------------------------------------------
// Compatibility shims expected by existing routes
// ------------------------------------------------------------

// Old helper: returns only URLs from a search
export async function fetchBingLinks(query: string): Promise<string[]> {
  const hits = await searchAu(query);
  return hits.map(h => h.url);
}

// Old helper: scrape name + size from a single product page URL
export async function scrapeProductInfo(url: string): Promise<{ name?: string; contents_size_weight?: string; url: string }> {
  const html = await fetchHtml(url);
  const $ = cheerio.load(html);
  const cand = extractNameAndSize($, url);
  return { ...cand, url };
}

// Old lifecycle hook imported by server/index.ts
let _puppeteerBrowser: any = null;

export async function closeBrowser(): Promise<void> {
  try {
    if (_puppeteerBrowser) {
      await _puppeteerBrowser.close();
      _puppeteerBrowser = null;
    }
  } catch {
    // swallow – this is a best-effort cleanup hook
  }
}
