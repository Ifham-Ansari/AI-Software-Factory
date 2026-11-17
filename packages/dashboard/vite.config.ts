import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The AI Software Factory server serves dist/ statically (index.html for unknown paths), so assets use relative URLs.
// `pnpm dev` proxies the API to a running `asf up` (ASF_URL, default http://127.0.0.1:4800).
const target = process.env.ASF_URL ?? "http://127.0.0.1:4800";

export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    chunkSizeWarningLimit: 1500,
  },
  server: {
    host: "127.0.0.1",
    proxy: {
      "/api": { target, ws: true, changeOrigin: false },
    },
  },
});
