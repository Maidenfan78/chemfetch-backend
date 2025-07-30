import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import rateLimit from 'express-rate-limit';
import pinoHttp from 'pino-http';

import logger from './utils/logger';

import scanRoute from './routes/scan';
import confirmRoute from './routes/confirm';
import sdsByNameRoute from './routes/sdsByName';
import healthRoute from './routes/health';

dotenv.config();

const app = express();

app.use(cors());
app.use(express.json({ limit: '15mb' }));
app.use(pinoHttp({ logger }));

const limiter = rateLimit({
  windowMs: 60 * 1000,
  max: 60,
});
app.use(limiter);

app.use('/scan', scanRoute);
app.use('/confirm', confirmRoute);
app.use('/sds-by-name', sdsByNameRoute);
app.use('/health', healthRoute);

export default app;
