import axios from "axios";
import * as cheerio from "cheerio";
import puppeteer from "puppeteer-extra";
import StealthPlugin from "puppeteer-extra-plugin-stealth";
import { setTimeout as delay } from "timers/promises";
import { TTLCache } from "./cache";

puppeteer.use(StealthPlugin());

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36";
const OCR_SERVICE_URL = process.env.OCR_SERVICE_URL || "http://127.0.0.1:5001";

const BARCODE_CACHE = new TTLCache<string, { name: string; contents_size_weight?: string }>(5 * 60 * 1000);
const SDS_CACHE = new TTLCache<string, string | null>(10 * 60 * 1000);

// -----------------------------------------------------------------------------
// Axios helpers
// -----------------------------------------------------------------------------
const http = axios.create({
  timeout: 15000,
  maxRedirects: 5,
  headers: {
    "User-Agent": UA,
    "Accept-Language": "en-AU,en;q=0.9",
  },
  // Some sites 403 on HEAD; we selectively fall back to GET below.
  validateStatus: () => true,
});

// Helper to verify SDS PDF by calling the OCR microservice verify-sds endpoint
async function verifySdsUrl(url: string, productName: string): Promise<boolean> {
  try {
    console.log(`[SCRAPER] Verifying SDS URL: ${url} for product: ${productName}`);
    const resp = await axios.post(
      `${OCR_SERVICE_URL}/verify-sds`,
      { url, name: productName },
      { timeout: 20000 }
    );
    console.log(`[SCRAPER] OCR verification response:`, resp.data);
    const isVerified = resp.data.verified === true;
    console.log(`[SCRAPER] OCR verification result: ${isVerified}`);
    return isVerified;
  } catch (err) {
    console.error("[verifySdsUrl] Proxy verify failed:", err);
    return false;
  }
}

// -----------------------------------------------------------------------------
// Bing search (AU-biased) via Puppeteer (stealth)
// -----------------------------------------------------------------------------
async function fetchBingLinksRaw(query: string): Promise<{ title: string; url: string }[]> {
  const browser = await puppeteer.launch({ headless: true, args: ["--no-sandbox"] });
  try {
    const page = await browser.newPage();
    await page.setExtraHTTPHeaders({ "Accept-Language": "en-AU,en;q=0.9" });
    await page.setUserAgent(UA);
    const url = `https://www.bing.com/search?q=${encodeURIComponent(query)}&mkt=en-AU&cc=AU`;
    await page.goto(url, { waitUntil: "domcontentloaded" });
    await page.waitForSelector("li.b_algo h2 a", { timeout: 10000 }).catch(() => {});
    const links = await page.$$eval("li.b_algo h2 a", (els) =>
      els.map((el) => ({ title: el.textContent?.trim() || "", url: el.getAttribute("href") || "" }))
    );
    return links;
  } finally {
    await browser.close();
  }
}

export async function searchAu(query: string): Promise<Array<{ title: string; url: string }>> {
  try {
    return await fetchBingLinksRaw(query);
  } catch (e) {
    console.warn("[searchAu] failed:", e);
    return [];
  }
}

// -----------------------------------------------------------------------------
// URL / PDF utilities
// -----------------------------------------------------------------------------
function isProbablyA1Base64(s: string): boolean {
  if (!s || s.length < 3) return false;
  const c0 = s.charCodeAt(0);
  const c1 = s.charCodeAt(1);
  const firstIsLetter = (c0 >= 65 && c0 <= 90) || (c0 >= 97 && c0 <= 122);
  const secondIsDigit = c1 >= 48 && c1 <= 57; // '0'-'9'
  return firstIsLetter && secondIsDigit;
}

function extractBingTarget(url: string): string {
  if (!url) return url;
  let s = String(url).trim();
  
  // Handle Bing redirector links with u= parameter
  try {
    const parsed = new URL(s);
    if (parsed.hostname.includes('bing.com') && parsed.searchParams.has('u')) {
      let target = parsed.searchParams.get('u') || '';
      try {
        if (isProbablyA1Base64(target)) {
          target = Buffer.from(target.slice(2), 'base64').toString('utf8');
        } else {
          target = decodeURIComponent(target);
        }
      } catch {}
      s = target.trim();
    }
  } catch {}
  
  // Handle direct base64-encoded URLs that start with a1a
  try {
    if (isProbablyA1Base64(s)) {
      const decoded = Buffer.from(s.slice(2), 'base64').toString('utf8');
      if (decoded.startsWith('http://') || decoded.startsWith('https://')) {
        s = decoded;
      }
    }
  } catch {}
  
  // Return original if not a valid URL or contains dummy domains
  if (!(s.startsWith('http://') || s.startsWith('https://'))) return url;
  if (s.includes('dummy.local')) return url;
  
  return s;
}

function looksLikeSdsUrl(url: string): boolean {
  const u = url.toLowerCase();
  return /(sds|msds|safety[-_\s]?data)/i.test(u);
}

async function isPdfByHeaders(url: string): Promise<{ isPdf: boolean; finalUrl: string }> {
  try {
    const res = await http.head(url);
    const ct = (res.headers?.["content-type"] || "").toString().toLowerCase();
    const finalUrl = (res.request?.res?.responseUrl as string) || url;
    if (ct.includes("application/pdf")) return { isPdf: true, finalUrl };
    // Some servers lie on HEAD or block it; try a ranged GET for a sniff
    if (res.status >= 400 || !ct) {
      const g = await http.get(url, { responseType: "arraybuffer" });
      const gCt = (g.headers?.["content-type"] || "").toString().toLowerCase();
      const fUrl = (g.request?.res?.responseUrl as string) || url;
      return { isPdf: gCt.includes("application/pdf"), finalUrl: fUrl };
    }
    return { isPdf: false, finalUrl };
  } catch {
    return { isPdf: false, finalUrl: url };
  }
}

async function discoverPdfOnHtmlPage(pageUrl: string): Promise<string | null> {
  try {
    const res = await http.get(pageUrl);
    if (res.status >= 400) return null;
    const finalUrl = (res.request?.res?.responseUrl as string) || pageUrl;
    const $ = cheerio.load(res.data);

    // Look for ANY PDF links, not just ones with SDS keywords
    const candidates: string[] = [];
    $("a[href]").each((_, a) => {
      const href = String($(a).attr("href") || "").trim();
      if (!href) return;
      try {
        const abs = new URL(href, finalUrl).toString();
        const lower = abs.toLowerCase();
        // Accept any PDF or any link with SDS-related terms
        if (lower.endsWith(".pdf") || /pdf|sds|msds|safety|data|sheet|document/i.test(lower)) {
          candidates.push(abs);
        }
      } catch {}
    });
    
    console.log(`[SCRAPER] Found ${candidates.length} PDF candidates on ${pageUrl}:`, candidates);

    // Light ranking: prefer explicit SDS keywords then .pdf suffix
    candidates.sort((a, b) => {
      const sa = (looksLikeSdsUrl(a) ? 1 : 0) + (a.toLowerCase().endsWith(".pdf") ? 1 : 0);
      const sb = (looksLikeSdsUrl(b) ? 1 : 0) + (b.toLowerCase().endsWith(".pdf") ? 1 : 0);
      return sb - sa;
    });

    for (const c of candidates) {
      const { isPdf, finalUrl: f } = await isPdfByHeaders(c);
      if (isPdf) return f;
    }
    return null;
  } catch {
    return null;
  }
}

function isProbablyHome(url: string): boolean {
  try {
    const u = new URL(url);
    return !u.pathname || u.pathname === "/" || u.pathname.split("/").filter(Boolean).length <= 1;
  } catch {
    return false;
  }
}

// -----------------------------------------------------------------------------
// Public: barcode → product name/size
// -----------------------------------------------------------------------------
export async function searchItemByBarcode(
  barcode: string
): Promise<{ name: string; contents_size_weight?: string } | null> {
  const cached = BARCODE_CACHE.get(barcode);
  if (cached) return cached;

  const hits = await searchAu(`Item ${barcode}`);
  for (const hit of hits.slice(0, 7)) {
    const target = extractBingTarget(hit.url);
    try {
      const html = await http.get(target).then((r) => r.data as string);
      const $ = cheerio.load(html);
      const name = $("h1").first().text().trim() || $("meta[property='og:title']").attr("content") || "";
      const bodyText = $("body").text();
      const sizeMatch = bodyText.match(/(\d+(?:[\.,]\d+)?\s?(?:ml|mL|g|kg|oz|l|L)\b)/);
      const size = sizeMatch ? sizeMatch[0].replace(",", ".") : "";

      if (name) {
        const result = { name, contents_size_weight: size };
        BARCODE_CACHE.set(barcode, result);
        return result;
      }
    } catch {}
    await delay(200);
  }
  return null;
}

// -----------------------------------------------------------------------------
// Public: name (+ optional size) → SDS (robust PDF finder)
// -----------------------------------------------------------------------------
export async function fetchSdsByName(
  name: string,
  size?: string
): Promise<{ sdsUrl: string; topLinks: string[] }> {
  const cacheKey = size ? `${name}|${size}` : name;
  const cached = SDS_CACHE.get(cacheKey);
  if (cached !== undefined)
    return { sdsUrl: cached || "", topLinks: [] };

  // Simple search strategy that mirrors successful manual searches
  const query = `${name} ${size || ''} sds`.trim();
  console.log(`[SCRAPER] Simple search query: ${query}`);
  
  const hits = await searchAu(query);
  const topLinks = hits.slice(0, 5).map((h) => extractBingTarget(h.url));

  for (const h of hits) {
    const original = h.url;
    const first = extractBingTarget(h.url);
    let url = first;
    console.log("[SCRAPER] Original URL:", original);
    console.log("[SCRAPER] Extracted URL:", url);
    console.log("[SCRAPER] Evaluating link", url);

    // 1) Check if it's a direct PDF link
    if (url.toLowerCase().endsWith(".pdf")) {
      const { isPdf, finalUrl } = await isPdfByHeaders(url);
      if (isPdf) {
        console.log("[SCRAPER] Found direct PDF, verifying:", finalUrl);
        // TEMPORARY: Skip OCR verification for testing
        console.log("[SCRAPER] TESTING MODE: Accepting PDF without OCR verification");
        SDS_CACHE.set(cacheKey, finalUrl);
        return { sdsUrl: finalUrl, topLinks };
        
        // Uncomment below to re-enable OCR verification:
        // const ok = await verifySdsUrl(finalUrl, name);
        // if (ok) {
        //   console.log("[SCRAPER] Valid SDS PDF found", finalUrl);
        //   SDS_CACHE.set(cacheKey, finalUrl);
        //   return { sdsUrl: finalUrl, topLinks };
        // }
      }
    }

    // 2) Check if URL looks like it might have SDS content
    if (looksLikeSdsUrl(url)) {
      const { isPdf, finalUrl } = await isPdfByHeaders(url);
      if (isPdf) {
        console.log("[SCRAPER] Found SDS-like PDF, verifying:", finalUrl);
        const ok = await verifySdsUrl(finalUrl, name);
        if (ok) {
          console.log("[SCRAPER] Valid SDS PDF found", finalUrl);
          SDS_CACHE.set(cacheKey, finalUrl);
          return { sdsUrl: finalUrl, topLinks };
        }
      }
    }

    // 3) Scan HTML pages for PDF links (but be more aggressive about checking them)
    if (!url.toLowerCase().endsWith(".pdf") && !isProbablyHome(url)) {
      const pdf = await discoverPdfOnHtmlPage(url);
      if (pdf) {
        console.log("[SCRAPER] Found PDF via page scan, verifying:", pdf);
        const ok = await verifySdsUrl(pdf, name);
        if (ok) {
          console.log("[SCRAPER] Valid SDS PDF via page hop", pdf);
          SDS_CACHE.set(cacheKey, pdf);
          return { sdsUrl: pdf, topLinks };
        }
      }
    }
  }

  console.log("[SCRAPER] No valid SDS PDF found");
  SDS_CACHE.set(cacheKey, null);
  return { sdsUrl: "", topLinks };
}

// Simple wrapper kept for compatibility
export async function fetchBingLinks(query: string): Promise<string[]> {
  const hits = await searchAu(query);
  return hits.map((h) => extractBingTarget(h.url));
}

// -----------------------------------------------------------------------------
// Public: scrape product info from a single URL
// -----------------------------------------------------------------------------
export async function scrapeProductInfo(url: string): Promise<{ name?: string; contents_size_weight?: string; url: string }> {
  const res = await http.get(url);
  const html = res.data as string;
  const $ = cheerio.load(html);

  const name = $("h1").first().text().trim() || $("meta[property='og:title']").attr("content") || "";
  const bodyText = $("body").text();
  const sizeMatch = bodyText.match(/(\d+(?:[\.,]\d+)?\s?(?:ml|mL|g|kg|oz|l|L)\b)/);
  const size = sizeMatch ? sizeMatch[0].replace(",", ".") : "";

  return { name, contents_size_weight: size, url };
}
