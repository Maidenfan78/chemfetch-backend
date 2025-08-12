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
    const resp = await axios.post(
      `${OCR_SERVICE_URL}/verify-sds`,
      { url, name: productName },
      { timeout: 20000 }
    );
    return resp.data.verified === true;
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
function extractBingTarget(url: string): string {
  // Bing redirector links often carry the true target in `u=`
  try {
    const u = new URL(url);
    const target = u.searchParams.get("u");
    if (target) return decodeURIComponent(target);
  } catch {}
  return url;
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

    // Prefer anchors that both end with .pdf and look like SDS
    const candidates: string[] = [];
    $("a[href]").each((_, a) => {
      const href = String($(a).attr("href") || "").trim();
      if (!href) return;
      try {
        const abs = new URL(href, finalUrl).toString();
        const lower = abs.toLowerCase();
        const isPdfSuffix = lower.endsWith(".pdf");
        if ((isPdfSuffix || looksLikeSdsUrl(lower)) && /pdf|sds|msds|safety/i.test(lower)) {
          candidates.push(abs);
        }
      } catch {}
    });

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
// Public: name → SDS (robust PDF finder)
// -----------------------------------------------------------------------------
export async function searchSdsByName(name: string): Promise<string | null> {
  const cached = SDS_CACHE.get(name);
  if (cached !== undefined) return cached;

  const hits = await searchAu(`${name} sds`);

  for (const h of hits) {
    const first = extractBingTarget(h.url);
    let url = first;
    console.log("[SCRAPER] Evaluating link", url);

    // 1) If URL ends with .pdf or is PDF by headers, and looks like SDS, verify it
    if (url.toLowerCase().endsWith(".pdf") || looksLikeSdsUrl(url)) {
      const { isPdf, finalUrl } = await isPdfByHeaders(url);
      if (isPdf) {
        if (!looksLikeSdsUrl(finalUrl)) {
          // keep a strong guard: require SDS keywords in the final URL to avoid random PDFs
          console.log("[SCRAPER] PDF without SDS keywords in URL → skip", finalUrl);
        } else {
          const ok = await verifySdsUrl(finalUrl, name);
          if (ok) {
            console.log("[SCRAPER] Valid SDS PDF found", finalUrl);
            SDS_CACHE.set(name, finalUrl);
            return finalUrl;
          }
        }
      }
    }

    // 2) One HTML hop: scan page for SDS PDFs
    if (!url.toLowerCase().endsWith(".pdf") && !isProbablyHome(url)) {
      const pdf = await discoverPdfOnHtmlPage(url);
      if (pdf) {
        const ok = await verifySdsUrl(pdf, name);
        if (ok) {
          console.log("[SCRAPER] Valid SDS PDF via page hop", pdf);
          SDS_CACHE.set(name, pdf);
          return pdf;
        }
      }
    }
  }

  console.log("[SCRAPER] No valid SDS PDF found");
  SDS_CACHE.set(name, null);
  return null;
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
