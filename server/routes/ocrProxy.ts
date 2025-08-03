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
  createProxyMiddleware({
    target: OCR_SERVICE_URL,
    changeOrigin: true,
    pathRewrite: (_path) => '/ocr', // always forward as /ocr
    headers: {
      // optional: identify source for logs
      'X-Forwarded-By': 'chemfetch-backend',
    },
  }),
);

export default router;