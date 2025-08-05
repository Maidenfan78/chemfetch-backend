// server/routes/scan.ts
import express from 'express';
import { supabase } from '../utils/supabaseClient';
import { fetchBingLinks, scrapeProductInfo } from '../utils/scraper';
import { isValidCode, isValidName } from '../utils/validation';
import logger from '../utils/logger';
import puppeteer from 'puppeteer-extra';
import StealthPlugin from 'puppeteer-extra-plugin-stealth';
import { load } from 'cheerio';
import axios from 'axios';

const router = express.Router();
puppeteer.use(StealthPlugin());

async function fetchSdsByName(name: string): Promise<{ sdsUrl: string, topLinks: string[] }> {
  const query = `${name} sds pdf`;
  const searchUrl = `https://www.bing.com/search?q=${encodeURIComponent(query)}`;

  logger.info({ term: query, searchUrl }, '[SCRAPER] SDS fallback Bing search (Puppeteer)');

  const browser = await puppeteer.launch({ headless: true, args: ['--no-sandbox'] });
  const page = await browser.newPage();
  await page.setUserAgent(
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
  );
  await page.goto(searchUrl, { waitUntil: 'domcontentloaded' });

  const links: string[] = await page.$$eval('li.b_algo h2 a', anchors => {
    return anchors.map(a => a.href).filter(Boolean);
  });

  const topLinks = links.slice(0, 5);

  for (const href of topLinks) {
    const isPdf = href.toLowerCase().includes('.pdf');
    const isJunk = new URL(href).hostname.includes('isocol.com.au');
    logger.info({ href, isPdf, isJunk }, '[SCRAPER] Evaluating SDS link');
    if (isPdf && !isJunk) {
      await browser.close();
      return { sdsUrl: href, topLinks };
    }
  }

  logger.info({ links }, '[SCRAPER] No matching SDS PDFs found');
  await browser.close();
  return { sdsUrl: '', topLinks };
}

router.post('/sds-by-name', async (req, res) => {
  const { name } = req.body;
  if (!isValidName(name)) return res.status(403).json({ error: 'Invalid name' });

  logger.info({ name }, '[SDS] Fetching by name');
  const { sdsUrl, topLinks } = await fetchSdsByName(name);
  logger.info({ name, sdsUrl, topLinks }, '[SDS] Fetched SDS URL and top links');
  res.json({ sdsUrl, topLinks });
});

router.post('/', async (req, res) => {
  const { code } = req.body;
  if (!isValidCode(code)) return res.status(403).json({ error: 'Invalid barcode' });
  logger.info({ code }, '[SCAN] Searching for barcode');

  const { data: existing, error: fetchErr } = await supabase
    .from('product')
    .select('*')
    .eq('barcode', code)
    .maybeSingle();

  if (fetchErr) return res.status(500).json({ error: fetchErr.message });

  if (existing) {
    let updated = { ...existing };

    if (!existing.sds_url && existing.name) {
      logger.info({ name: existing.name }, '[SCAN] Fetching missing SDS URL for existing product');
      const { sdsUrl: foundSds } = await fetchSdsByName(existing.name);
      logger.info({ name: existing.name, foundSds }, '[SCAN] Fallback SDS result');
      if (foundSds) {
        const updateResult = await supabase.from('product').update({ sds_url: foundSds }).eq('barcode', code).select().maybeSingle();
        logger.info({ updateResult }, '[SCAN] Updated product with SDS');
        updated.sds_url = foundSds;
      }
    }

    logger.info({ code, updated }, '[SCAN] Returning existing product with updated SDS');
    return res.json({
      code,
      product: updated,
      scraped: [{
        url: '',
        name: updated.name || '',
        size: updated.contents_size_weight || '',
        sdsUrl: updated.sds_url || '',
      }],
      message: 'Item already in database',
    });
  }

  const urls = await fetchBingLinks(code);
  logger.info({ code, urls }, '[SCAN] Scraping product info from URLs');
  const scraped = (await Promise.all(urls.map(scrapeProductInfo))).filter(Boolean);
  logger.info({ code, scraped }, '[SCAN] Scraped results');
  const top = scraped[0] || { name: '', size: '', sdsUrl: '' };

  logger.info({ top }, '[SCAN] Top scraped result');

  if (!top.sdsUrl && top.name) {
    logger.info({ name: top.name }, '[SCAN] Fetching SDS URL via fallback');
    const { sdsUrl: fallbackSds, topLinks } = await fetchSdsByName(top.name);
    logger.info({ name: top.name, fallbackSds, topLinks }, '[SCAN] Fallback SDS result');
    if (fallbackSds) top.sdsUrl = fallbackSds;
  }

  const insert = await supabase
    .from('product')
    .upsert({
      barcode: code,
      name: top.name,
      contents_size_weight: top.size,
      sds_url: top.sdsUrl || null,
    })
    .select()
    .maybeSingle();

  const data = insert.data;
  const error = insert.error;

  logger.info({ code, data, error }, '[SCAN] Final database write result');
  if (error) return res.status(500).json({ error: error.message });

  return res.json({ code, scraped, product: data });
});

export default router;
