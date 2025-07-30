import request from 'supertest';

process.env.SB_URL = 'http://localhost';
process.env.SB_SERVICE_KEY = 'key';

jest.mock('../server/utils/supabaseClient', () => ({ supabase: { from: jest.fn() } }));

function setupSupabase(response: {data: any; error: any}) {
  const { supabase } = require('../server/utils/supabaseClient');
  const chain: any = {};
  chain.update = jest.fn(() => chain);
  chain.eq = jest.fn(() => chain);
  chain.select = jest.fn(() => chain);
  chain.maybeSingle = jest.fn(() => Promise.resolve(response));
  (supabase.from as jest.Mock).mockReturnValue(chain);
}

afterEach(() => {
  jest.clearAllMocks();
});

test('POST /confirm returns 403 without code', async () => {
  const app = (await import('../server/app')).default;
  const res = await request(app).post('/confirm').send({});
  expect(res.status).toBe(403);
});

test('POST /confirm updates product', async () => {
  setupSupabase({ data: { barcode: '123', product_name: 'New', contents_size_weight: '10ml' }, error: null });
  const app = (await import('../server/app')).default;

  const res = await request(app).post('/confirm').send({ code: '123', name: 'New', size: '10ml' });

  expect(res.status).toBe(200);
  expect(res.body.success).toBe(true);
  expect(res.body.product.product_name).toBe('New');
});
