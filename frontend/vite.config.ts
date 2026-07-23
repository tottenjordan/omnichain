import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The FastAPI backend serves the built SPA in production. During `vite dev`
// we proxy /api to the local uvicorn server so both run side by side.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    // Emit into the backend package so the Docker image can serve it statically.
    outDir: "dist",
  },
});
