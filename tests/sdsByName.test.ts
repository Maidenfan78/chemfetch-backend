import request from 'supertest';

process.env.SB_URL = 'http://localhost';
process.env.SB_SERVICE_KEY = 'key';

jest.mock('../server/utils/scraper', () => ({ searchSdsByName: jest.fn() }));

afterEach(() => {
  jest.clearAllMocks();
});

test('POST /sds-by-name requires name', async () => {
  const app = (await import('../server/app')).default;
  const res = await request(app).post('/sds-by-name').send({});
  expect(res.status).toBe(400);
});

test('POST /sds-by-name returns URL', async () => {
  const { searchSdsByName } = require('../server/utils/scraper');
  (searchSdsByName as jest.Mock).mockResolvedValue({ url: 'http://example.com/sds.pdf', verified: true });
  const app = (await import('../server/app')).default;
  const res = await request(app).post('/sds-by-name').send({ name: 'test' });
  expect(res.status).toBe(200);
  expect(res.body.sdsUrl).toBe('http://example.com/sds.pdf');
  expect(res.body.verified).toBe(true);
});
