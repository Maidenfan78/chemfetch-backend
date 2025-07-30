// server/index.ts
import app from './app';
import { closeBrowser } from './utils/scraper';

const PORT = process.env.PORT || 3000;

app.listen(PORT, () => console.log(`Backend API listening on port ${PORT}`));

// Handle shutdown gracefully
process.on('SIGINT', () => closeBrowser().finally(() => process.exit()));
process.on('SIGTERM', () => closeBrowser().finally(() => process.exit()));
