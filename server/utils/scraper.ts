/*
  scraper.ts — AU‏‑biased search helpers and SDS logic
  ---------------------------------------------------
  Exports:
    - searchAu(query)
    - searchItemByBarcode(barcode)
    - searchSdsByName(name)
    - fetchBingLinks(query)
    - scrapeProductInfo(url)

  Dependencies (install if missing):
    npm i axios cheerio undici
*/

import axios, { AxiosRequestConfig } from "axios";
import * as cheerio from "cheerio";
import { setTimeout as delay } from "timers/promises";
import { TTLCache } from "./cache";

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36";

const OCR_SERVICE_URL = process.env.OCR_SERVICE_URL || "http://127.0.0.1:5001";

const BARCODE_CACHE = new TTLCache<string, { name: string; contents_size_weight?: string }>(5 * 60 * 1000); // 5 min
const SDS_CACHE = new TTLCache<string, string | null>(10 * 60 * 1000); // 10 min

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
  return u.toString();
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

async function fetchHtml(url: string, cfg: AxiosRequestConfig = {}) {
  const res = await axios.get<string>(withAuParams(url), {
    ...cfg,
    headers: { ...(cfg.headers || {}), ...auHeaders() },
    timeout: 12000,
    maxRedirects: 5,
    validateStatus: (s) => s >= 200 && s < 400,
  });
  return res.data as string;
}

export async function searchAu(query: string): Promise<Array<{ title: string; url: string }>> {
  const results: Array<{ title: string; url: string }> = [];
  try {
    const q = encodeURIComponent(query);
    const html = await fetchHtml(`https://www.bing.com/search?q=${q}&mkt=en-AU&cc=AU`);
    const $ = cheerio.load(html);
    $("li.b_algo h2 a, .b_algo h2 a").each((_, el) => {
      const title = $(el).text().trim();
      const raw = $(el).attr("href") || "";
      if (!raw) return;
      results.push({ title, url: raw });
    });
  } catch (err) {
    // ignore
  }
  return dedupe(results);
}

export async function searchItemByBarcode(barcode: string): Promise<{ name: string; contents_size_weight?: string } | null> {
  const cached = BARCODE_CACHE.get(barcode);
  if (cached) return cached;

  const queries = [`Item ${barcode}`, `product ${barcode}`];

  for (const query of queries) {
    const hits = await searchAu(query);
    for (const hit of hits.slice(0, 8)) {
      try {
        const html = await fetchHtml(hit.url);
        const $ = cheerio.load(html);

        const texts: string[] = [];
        const h1 = $("h1").first().text().trim();
        if (h1) texts.push(h1);
        const ogTitle = $('meta[property="og:title"]').attr("content")?.trim();
        if (ogTitle) texts.push(ogTitle);
        const title = $("title").text().trim();
        if (title) texts.push(title);

        const joined = texts.join(" • ");
        const name = joined.trim();
        const size = joined.match(/\b(\d+(?:\.\d+)?)\s?(mL|L|g|kg)\b/i)?.[0];

        if (name) {
          const result = { name, contents_size_weight: size };
          BARCODE_CACHE.set(barcode, result);
          return result;
        }
      } catch {
        // try next
      }
      await delay(250);
    }
  }
  return null;
}

export async function searchSdsByName(name: string): Promise<string | null> {
  const cached = SDS_CACHE.get(name);
  if (cached !== undefined) return cached;

  const hits = await searchAu(`${name} sds`);
  const pdfs = hits.filter(h => h.url.endsWith('.pdf'));

  for (const h of pdfs.slice(0, 8)) {
    try {
      const verifyRes = await axios.post(`${OCR_SERVICE_URL}/verify-sds`, { url: h.url, name }, {
        headers: { "Content-Type": "application/json", ...auHeaders() },
        timeout: 15000
      });
      if (verifyRes.data.verified) {
        SDS_CACHE.set(name, h.url);
        return h.url;
      }
    } catch {
      // try next
    }
    await delay(200);
  }

  SDS_CACHE.set(name, null);
  return null;
}

export async function fetchBingLinks(query: string): Promise<string[]> {
  const hits = await searchAu(query);
  return hits.map(h => h.url);
}

export async function scrapeProductInfo(url: string): Promise<{ name?: string; contents_size_weight?: string; url: string }> {
  const html = await fetchHtml(url);
  const $ = cheerio.load(html);

  const texts: string[] = [];
  const h1 = $("h1").first().text().trim();
  if (h1) texts.push(h1);
  const ogTitle = $('meta[property="og:title"]').attr("content")?.trim();
  if (ogTitle) texts.push(ogTitle);
  const title = $("title").text().trim();
  if (title) texts.push(title);

  const joined = texts.join(" • ");
  const name = joined.trim();
  const size = joined.match(/\b(\d+(?:\.\d+)?)\s?(mL|L|g|kg)\b/i)?.[0];

  return { name, contents_size_weight: size, url };
}
