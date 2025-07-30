// server/index.ts
import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import { closeBrowser } from './utils/scraper';

import scanRoute from './routes/scan';
import ocrRoute from './routes/ocr';
import confirmRoute from './routes/confirm';
import sdsByNameRoute from './routes/sdsByName';

dotenv.config();

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json({ limit: '15mb' }));

// API Routes
app.use('/scan', scanRoute);
app.use('/ocr', ocrRoute);
app.use('/confirm', confirmRoute);
app.use('/sds-by-name', sdsByNameRoute);

app.listen(PORT, () => console.log(`Backend API listening on port ${PORT}`));

// Handle shutdown gracefully
process.on('SIGINT', () => closeBrowser().finally(() => process.exit()));
process.on('SIGTERM', () => closeBrowser().finally(() => process.exit()));
