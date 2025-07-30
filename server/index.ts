// server/index.ts
import app from './app';
import { closeBrowser } from './utils/scraper';
import logger from './utils/logger';

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => logger.info(`Backend API listening on port ${PORT}`));

// Handle shutdown gracefully
process.on('SIGINT', () => closeBrowser().finally(() => process.exit()));
process.on('SIGTERM', () => closeBrowser().finally(() => process.exit()));
