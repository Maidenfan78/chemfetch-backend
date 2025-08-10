import request from 'supertest';

process.env.SB_URL = 'http://localhost';
process.env.SB_SERVICE_KEY = 'key';

jest.mock('../server/utils/supabaseClient', () => ({ supabase: { from: jest.fn() } }));
jest.mock('../server/utils/scraper', () => ({
  searchItemByBarcode: jest.fn(),
  searchSdsByName: jest.fn(),
}));

function setupSupabase(responses: Array<{ data: any; error: any }>) {
  const { supabase } = require('../server/utils/supabaseClient');
  const chains = responses.map((resp) => {
    const chain: any = {};
    chain.select = jest.fn(() => chain);
    chain.eq = jest.fn(() => chain);
    chain.update = jest.fn(() => chain);
    chain.upsert = jest.fn(() => chain);
    chain.maybeSingle = jest.fn(() => Promise.resolve(resp));
    return chain;
  });
  (supabase.from as jest.Mock).mockImplementation(() => chains.shift());
}

afterEach(() => {
  jest.clearAllMocks();
});

test('POST /scan returns 403 without code', async () => {
  const app = (await import('../server/app')).default;
  const res = await request(app).post('/scan').send({});
  expect(res.status).toBe(403);
});

test('POST /scan returns existing product and updates SDS', async () => {
  setupSupabase([
    { data: { barcode: '123', name: 'Test', contents_size_weight: '50ml', sds_url: null }, error: null },
    { data: { barcode: '123', name: 'Test', contents_size_weight: '50ml', sds_url: 'http://sds.com/test.pdf' }, error: null },
  ]);
  const { searchSdsByName } = require('../server/utils/scraper');
  (searchSdsByName as jest.Mock).mockResolvedValue({ url: 'http://sds.com/test.pdf', verified: true });
  const app = (await import('../server/app')).default;

  const res = await request(app).post('/scan').send({ code: '123' });

  expect(res.status).toBe(200);
  expect(res.body.product.sds_url).toBe('http://sds.com/test.pdf');
  expect(res.body.message).toBeDefined();
});
