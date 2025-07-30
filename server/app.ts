import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';

import scanRoute from './routes/scan';
import confirmRoute from './routes/confirm';
import sdsByNameRoute from './routes/sdsByName';

dotenv.config();

const app = express();

app.use(cors());
app.use(express.json({ limit: '15mb' }));

app.use('/scan', scanRoute);
app.use('/confirm', confirmRoute);
app.use('/sds-by-name', sdsByNameRoute);

export default app;
