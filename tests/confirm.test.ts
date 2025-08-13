import request from 'supertest';

process.env.SB_URL = 'http://localhost';
process.env.SB_SERVICE_KEY = 'key';

jest.mock('../server/utils/supabaseClient', () => ({ supabase: { from: jest.fn() } }));

function setupSupabase(existing: any, upsertResult?: any) {
  const { supabase } = require('../server/utils/supabaseClient');

  const selectChain: any = {};
  selectChain.select = jest.fn(() => selectChain);
  selectChain.eq = jest.fn(() => selectChain);
  selectChain.maybeSingle = jest.fn(() => Promise.resolve({ data: existing, error: null }));

  (supabase.from as jest.Mock).mockReturnValueOnce(selectChain);

  if (upsertResult) {
    const upsertChain: any = {};
    upsertChain.upsert = jest.fn(() => upsertChain);
    upsertChain.select = jest.fn(() => upsertChain);
    upsertChain.maybeSingle = jest.fn(() => Promise.resolve({ data: upsertResult, error: null }));
    (supabase.from as jest.Mock).mockReturnValueOnce(upsertChain);
  }
}

afterEach(() => {
  jest.clearAllMocks();
});

test('POST /confirm returns 403 without code', async () => {
  const app = (await import('../server/app')).default;
  const res = await request(app).post('/confirm').send({});
  expect(res.status).toBe(403);
});

test('POST /confirm upserts product when details change', async () => {
  setupSupabase(
    { barcode: '123', name: 'Old', contents_size_weight: '5ml' },
    { barcode: '123', name: 'New', contents_size_weight: '10ml' }
  );
  const app = (await import('../server/app')).default;

  const res = await request(app).post('/confirm').send({ code: '123', name: 'New', size: '10ml' });

  expect(res.status).toBe(200);
  expect(res.body.success).toBe(true);
  expect(res.body.product.name).toBe('New');
});

test('POST /confirm returns 409 for duplicate product', async () => {
  setupSupabase({ barcode: '123', name: 'New', contents_size_weight: '10ml' });
  const app = (await import('../server/app')).default;

  const res = await request(app).post('/confirm').send({ code: '123', name: 'New', size: '10ml' });

  expect(res.status).toBe(409);
  expect(res.body.error).toBe('Product already registered');
});
