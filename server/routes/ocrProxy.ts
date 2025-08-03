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
    (
      {
        target: OCR_SERVICE_URL,
        changeOrigin: true,
        pathRewrite: () => '/ocr', // always forward as /ocr

        // @ts-ignore: logLevel is supported by http-proxy-middleware but missing from our d.ts
        logLevel: 'debug',

        onProxyReq: (proxyReq, req, res) => {
          console.log(
            '[OCR Proxy] ProxyReq:',
            new Date().toISOString(),
            req.method,
            '→',
            `${OCR_SERVICE_URL}/ocr`,
            'headers:',
            req.headers
          );
        },

        onProxyRes: (proxyRes, req, res) => {
          console.log(
            '[OCR Proxy] ProxyRes:',
            new Date().toISOString(),
            'status:',
            proxyRes.statusCode,
            'headers:',
            proxyRes.headers
          );
        },

        headers: {
          'X-Forwarded-By': 'chemfetch-backend',
        },
      } as any
    )
  )
);

export default router;
