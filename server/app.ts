// server/app.ts
import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import rateLimit from 'express-rate-limit';
import pinoHttp from 'pino-http';
import sdsByNameRoute from './routes/sdsByName';
import parseSdsRoute from './routes/parseSds';
import batchSdsRoute from './routes/batchSds';

import logger from './utils/logger';

import scanRoute from './routes/scan';
import confirmRoute from './routes/confirm';
import healthRoute from './routes/health';
import ocrProxy from './routes/ocrProxy';      // <— NEW
import verifySdsProxy from './routes/verifySds'; // <— NEW

dotenv.config();

const app = express();

app.use(cors());
app.use(express.json({ limit: '15mb' }));
app.use('/sds-by-name', sdsByNameRoute);
app.use(pinoHttp({ logger }));

const limiter = rateLimit({ windowMs: 60_000, max: 60 });
app.use(limiter);

app.use('/scan', scanRoute);
app.use('/confirm', confirmRoute);
app.use('/health', healthRoute);
app.use('/ocr', ocrProxy);                     // <— NEW
app.use('/verify-sds', verifySdsProxy);        // <— NEW
app.use('/parse-sds', parseSdsRoute);
app.use('/batch-sds', batchSdsRoute);          // <— NEW

export default app;