import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const buildId = process.env.VITE_BUILD_ID || "dev";

export default defineConfig({
  define: {
    __BUILD_ID__: JSON.stringify(buildId),
  },
  plugins: [
    react(),
    {
      name: "html-build-id",
      transformIndexHtml(html) {
        return html.replace("<html", `<html data-build="${buildId}"`);
      },
    },
  ],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
