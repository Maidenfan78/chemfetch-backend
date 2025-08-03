// server/index.ts
import app from "./app";
import { closeBrowser } from "./utils/scraper";
import logger from "./utils/logger";
import ocrProxy from "./routes/ocrProxy";

// ---------------------------------------------------------------------------
// 🔀  /ocr proxy → Python service (127.0.0.1:5001)
// ---------------------------------------------------------------------------
// This keeps port 3000 as the single public endpoint so that mobile clients
// don't need direct access to :5001. The multipart body streams straight
// through without buffering.
app.use(
  "/ocr",
  // Log incoming proxy requests
  (req, res, next) => {
    logger.info("[OCR Proxy Incoming]", {
      timestamp: new Date().toISOString(),
      method: req.method,
      url: req.originalUrl,
      headers: req.headers,
    });
    next();
  },
  ocrProxy
);

// ---------------------------------------------------------------------------
// 🩺  Health check (also verifies proxy path)
// ---------------------------------------------------------------------------
app.get("/ocr/health", (_req, res) =>
  res.json({ status: "ok", target: "127.0.0.1:5001" })
);

// ---------------------------------------------------------------------------
// 🏁  Start server
// ---------------------------------------------------------------------------
const PORT = process.env.PORT || 3000;
app.listen(PORT, () =>
  logger.info(`Backend API listening on port ${PORT}`)
);

// ---------------------------------------------------------------------------
// 🛑  Graceful shutdown
// ---------------------------------------------------------------------------
process.on("SIGINT", () =>
  closeBrowser().finally(() => process.exit())
);
process.on("SIGTERM", () =>
  closeBrowser().finally(() => process.exit())
);
