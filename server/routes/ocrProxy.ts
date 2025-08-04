// server/routes/ocrProxy.ts
import { Router } from 'express';
import { createProxyMiddleware } from 'http-proxy-middleware';
import dotenv from 'dotenv';

dotenv.config();

/**
 * Forwards multipart `/ocr` POST requests to the Python service.
 * The proxy streams the body so we don’t need extra middleware.
 */
const OCR_SERVICE_URL = process.env.OCR_SERVICE_URL || 'http://localhost:5001';
const router = Router();

router.use(
  '/',
  createProxyMiddleware(
    {
      target: OCR_SERVICE_URL,
      changeOrigin: true,
      pathRewrite: () => '/ocr', // always forward as /ocr

      // @ts-ignore: logLevel is supported by http-proxy-middleware but missing from our d.ts
      logLevel: 'debug',

      onProxyReq: (proxyReq, req, res) => {
        console.log(
          '[OCR Proxy ▶︎ Python]',
          new Date().toISOString(),
          'method:', proxyReq.method,
          'path:', proxyReq.path,
          'content-type:', proxyReq.getHeader('content-type'),
          'content-length:', proxyReq.getHeader('content-length')
        );
      },

      onProxyRes: (proxyRes, req, res) => {
        console.log(
          '[OCR Python ◀︎ Proxy]',
          new Date().toISOString(),
          'status:', proxyRes.statusCode,
          'headers:', proxyRes.headers
        );
      },

      headers: {
        'X-Forwarded-By': 'chemfetch-backend',
      },
    } as any
  )
);

export default router;
