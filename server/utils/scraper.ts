// server/utils/scraper.ts
import axios from 'axios';
import puppeteer from 'puppeteer';
import type { Browser, LaunchOptions } from 'puppeteer';
import { load } from 'cheerio';
import { addExtra } from 'puppeteer-extra';
import StealthPlugin from 'puppeteer-extra-plugin-stealth';

const pptr = addExtra(puppeteer);
pptr.use(StealthPlugin());

let browserPromise: Promise<Browser> | null = null;

export async function getBrowser(): Promise<Browser> {
  if (!browserPromise) {
    const launchOptions: LaunchOptions = {
      headless: true,
      args: ['--no-sandbox', '--ignore-certificate-errors'],
    };
    browserPromise = pptr.launch(launchOptions);
  }
  return browserPromise;
}

export async function closeBrowser() {
  if (browserPromise) {
    try {
      const browser = await browserPromise;
      await browser.close();
    } catch {}
    browserPromise = null;
  }
}

export async function fetchBingLinks(term: string): Promise<string[]> {
  try {
    const browser = await getBrowser();
    const page = await browser.newPage();
    await page.setExtraHTTPHeaders({ 'Accept-Language': 'en-AU,en;q=0.9' });
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64)...');
    await page.setRequestInterception(true);
    page.on('request', req => {
      if (["image", "stylesheet", "font", "media"].includes(req.resourceType())) req.abort();
      else req.continue();
    });
    await page.goto(`https://www.bing.com/search?q=${encodeURIComponent(term)}`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('li.b_algo h2 a', { timeout: 10000 });
    const links = await page.$$eval('li.b_algo h2 a', els => els.map(a => a.href).slice(0, 5));
    await page.close();
    return links;
  } catch {
    return fetchBingLinksFallback(term);
  }
}

export async function fetchBingLinksFallback(term: string): Promise<string[]> {
  try {
    const res = await axios.get(`https://www.bing.com/search?q=${encodeURIComponent(term)}`, {
      headers: { 'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'en-AU' },
    });
    const $ = load(res.data);
    const urls: string[] = [];
    $('li.b_algo h2 a').each((_, el) => {
      const href = $(el).attr('href');
      if (href?.startsWith('http') && urls.length < 5) urls.push(href);
    });
    return urls;
  } catch {
    return [];
  }
}

export async function scrapeProductInfo(url: string): Promise<{ url: string; name: string; size: string; sdsUrl: string } | null> {
  try {
    const { data } = await axios.get(url, {
      headers: { 'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'en-AU', Referer: 'https://www.bing.com/' },
      timeout: 20000,
    });
    const $ = load(data);
    const name = $('h1').first().text().trim() || '';
    const sizeMatch = $('body').text().match(/(\d+(?:\.\d+)?\s?(?:ml|g|kg|oz|l))/i);
    const size = sizeMatch ? sizeMatch[0] : '';

    const sdsLinks = $('a').map((_, a) => {
      const href = ($(a).attr('href') || '').trim();
      const text = ($(a).text() || '').toLowerCase();
      if (!/\.pdf$/i.test(href)) return null;
      if (!/(sds|msds|safety)/i.test(href + text)) return null;
      return href.startsWith('http') ? href : new URL(href, url).href;
    }).get();

    const sdsUrl = sdsLinks.length ? sdsLinks[0] : '';
    return { url, name, size, sdsUrl };
  } catch {
    return null;
  }
}

export async function fetchSdsByName(name: string): Promise<string> {
  const query = `${name} sds pdf`;
  const links = await fetchBingLinks(query);
  for (const link of links) {
    if (link.endsWith('.pdf')) return link;
  }
  return '';
}
