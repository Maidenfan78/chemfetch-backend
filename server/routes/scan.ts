import express from 'express';
import { supabase } from '../utils/supabaseClient';
import { fetchBingLinks, scrapeProductInfo } from '../utils/scraper';
import { isValidCode, isValidName } from '../utils/validation';
import logger from '../utils/logger';
import puppeteer from 'puppeteer-extra';
import StealthPlugin from 'puppeteer-extra-plugin-stealth';

const router = express.Router();
puppeteer.use(StealthPlugin());

export type ScrapedProduct = {
  name?: string;
  contents_size_weight?: string;
  url: string;
  size?: string;
  sdsUrl?: string;
};

// --- Helpers -----------------------------------------------------------------
function isProbablyA1Base64(s: string): boolean {
  if (!s || s.length < 3) return false;
  const c0 = s.charCodeAt(0);
  const c1 = s.charCodeAt(1);
  const firstIsLetter = (c0 >= 65 && c0 <= 90) || (c0 >= 97 && c0 <= 122);
  const secondIsDigit = c1 >= 48 && c1 <= 57; // '0'-'9'
  return firstIsLetter && secondIsDigit;
}

function normaliseUrl(u: string): string | null {
  if (!u) return null;
  let s = String(u).trim();
  try {
    if (isProbablyA1Base64(s)) {
      const decoded = Buffer.from(s.slice(2), 'base64').toString('utf8');
      if (decoded.startsWith('http://') || decoded.startsWith('https://')) s = decoded;
    }
  } catch {}
  if (!(s.startsWith('http://') || s.startsWith('https://'))) return null;
  if (s.includes('dummy.local')) return null; // kill placeholder host
  return s;
}

async function fetchSdsByName(name: string): Promise<{ sdsUrl: string; topLinks: string[] }> {
  const query = `${name} sds pdf`;
  const searchUrl = `https://www.bing.com/search?q=${encodeURIComponent(query)}&mkt=en-AU&cc=AU`;
  logger.info({ term: query, searchUrl }, '[SCRAPER] SDS fallback Bing search (Puppeteer)');

  let browser: any;
  try {
    browser = await puppeteer.launch({ headless: true, args: ['--no-sandbox'] });
    const page = await browser.newPage();
    await page.setUserAgent(
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    );
    await page.goto(searchUrl, { waitUntil: 'domcontentloaded', timeout: 20000 });

    const links: string[] = await page.$$eval('li.b_algo h2 a', (anchors) =>
      anchors.map((a: any) => a.href).filter(Boolean)
    );
    const topLinks = links.slice(0, 5);

    for (const href of topLinks) {
      const url = normaliseUrl(href);
      if (!url) continue;
      const isPdf = url.toLowerCase().includes('.pdf');
      const host = new URL(url).hostname;
      const isJunk = host.includes('isocol.com.au');
      logger.info({ href: url, isPdf, isJunk }, '[SCRAPER] Evaluating SDS link');
      if (isPdf && !isJunk) {
        return { sdsUrl: url, topLinks };
      }
    }

    logger.info({ links }, '[SCRAPER] No matching SDS PDFs found');
    return { sdsUrl: '', topLinks };
  } catch (err: any) {
    logger.warn({ err: String(err) }, '[SCRAPER] Puppeteer SDS search failed');
    return { sdsUrl: '', topLinks: [] };
  } finally {
    try { await browser?.close(); } catch {}
  }
}

// --- Routes ------------------------------------------------------------------
router.post('/sds-by-name', async (req, res) => {
  const { name } = req.body || {};
  if (!isValidName(name)) return res.status(403).json({ error: 'Invalid name' });

  try {
    logger.info({ name }, '[SDS] Fetching by name');
    const { sdsUrl, topLinks } = await fetchSdsByName(name);
    logger.info({ name, sdsUrl, topLinks }, '[SDS] Fetched SDS URL and top links');
    return res.json({ sdsUrl, topLinks });
  } catch (err: any) {
    logger.error({ err: String(err), name }, '[SDS] Failed');
    return res.status(502).json({ error: 'SDS_LOOKUP_FAILED', message: String(err?.message || err) });
  }
});

router.post('/', async (req, res) => {
  const { code } = req.body || {};
  if (!isValidCode(code)) return res.status(403).json({ error: 'Invalid barcode' });
  logger.info({ code }, '[SCAN] Searching for barcode');

  try {
    // 1) DB lookup first
    const { data: existing, error: fetchErr } = await supabase
      .from('product')
      .select('*')
      .eq('barcode', code)
      .maybeSingle();

    if (fetchErr) return res.status(500).json({ error: fetchErr.message });

    if (existing) {
      let updated = { ...existing } as typeof existing & { sds_url?: string };

      if (!existing.sds_url && existing.name) {
        try {
          logger.info({ name: existing.name }, '[SCAN] Fetching missing SDS URL for existing product');
          const { sdsUrl: foundSds } = await fetchSdsByName(existing.name);
          logger.info({ name: existing.name, foundSds }, '[SCAN] Fallback SDS result');
          if (foundSds) {
            const updateResult = await supabase
              .from('product')
              .update({ sds_url: foundSds })
              .eq('barcode', code)
              .select()
              .maybeSingle();
            logger.info({ updateResult }, '[SCAN] Updated product with SDS');
            updated.sds_url = foundSds;
          }
        } catch (err: any) {
          logger.warn({ err: String(err) }, '[SCAN] SDS enrichment failed');
        }
      }

      logger.info({ code, updated }, '[SCAN] Returning existing product with updated SDS');
      return res.json({
        code,
        product: updated,
        scraped: [
          { url: '', name: updated.name || '', size: updated.contents_size_weight || '', sdsUrl: updated.sds_url || '' },
        ],
        message: 'Item already in database',
      });
    }

    // 2) Web scrape on DB miss
    const urls = await fetchBingLinks(code);
    logger.info({ code, rawUrls: urls }, '[SCAN] Raw URLs from search');

    const cleaned = [...new Set((urls || []).map(normaliseUrl).filter(Boolean))] as string[];
    logger.info({ code, cleaned }, '[SCAN] Normalised URLs for scraping');

    const scraped = await Promise.all(
      cleaned.map(async (u) => {
        try {
          const r = (await scrapeProductInfo(u)) as ScrapedProduct;
          return r;
        } catch (err: any) {
          logger.warn({ url: u, err: String(err) }, '[SCAN] scrape failed');
          return { url: u, name: '', size: '', sdsUrl: '' };
        }
      })
    );

    logger.info({ code, scraped }, '[SCAN] Scraped results');
    const top: ScrapedProduct = scraped.find((s) => s?.name) || { name: '', size: '', sdsUrl: '', url: '' };
    logger.info({ top }, '[SCAN] Top scraped result');

    if (!top.sdsUrl && top.name) {
      try {
        logger.info({ name: top.name }, '[SCAN] Fetching SDS URL via fallback');
        const { sdsUrl: fallbackSds, topLinks } = await fetchSdsByName(top.name);
        logger.info({ name: top.name, fallbackSds, topLinks }, '[SCAN] Fallback SDS result');
        if (fallbackSds) top.sdsUrl = fallbackSds;
      } catch (err: any) {
        logger.warn({ name: top.name, err: String(err) }, '[SCAN] SDS fallback failed');
      }
    }

    const insert = await supabase
      .from('product')
      .upsert({
        barcode: code,
        name: top.name || null,
        contents_size_weight: top.size ?? top.contents_size_weight ?? null,
        sds_url: top.sdsUrl || null,
      })
      .select()
      .maybeSingle();

    const data = insert.data;
    const error = insert.error;

    logger.info({ code, data, error }, '[SCAN] Final database write result');
    if (error) return res.status(500).json({ error: error.message });

    return res.json({ code, scraped, product: data });
  } catch (err: any) {
    logger.error({ code, err: String(err) }, '[SCAN] failed');
    return res.status(502).json({ error: 'SCAN_FAILED', message: String(err?.message || err) });
  }
});

export default router;