import request from 'supertest';

process.env.SB_URL = 'http://localhost';
process.env.SB_SERVICE_KEY = 'key';

test('GET /health returns status', async () => {
  const app = (await import('../server/app')).default;
  const res = await request(app).get('/health');
  expect(res.status).toBe(200);
  expect(res.body.status).toBe('ok');
  expect(typeof res.body.uptime).toBe('number');
});
