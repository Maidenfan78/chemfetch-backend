import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import rateLimit from 'express-rate-limit';
import pinoHttp from 'pino-http';
import sdsByNameRoute from './routes/sdsByName';

import logger from './utils/logger';

import scanRoute from './routes/scan';
import confirmRoute from './routes/confirm';
import healthRoute from './routes/health';
import ocrProxy from './routes/ocrProxy';      // <— NEW

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

export default app;