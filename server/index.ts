// server/index.ts
import app from "./app";
import logger from "./utils/logger";

// Note: OCR route registration is now handled in app.ts to avoid duplicate registration
// The proxy configuration is properly centralized in the main app configuration.

// ---------------------------------------------------------------------------
// 🩺  Health check (verifies proxy path)
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
process.on("SIGINT", () => process.exit());
process.on("SIGTERM", () => process.exit());

