import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { loadBankConfig } from "./scripts/bank-config.mjs";

export default defineConfig(() => {
  // Also guard direct `vite` invocations that bypass npm lifecycle hooks.
  const bank = loadBankConfig(fileURLToPath(new URL(".", import.meta.url)));
  const virtualId = "virtual:bank-config";
  const resolvedId = `\0${virtualId}`;
  return {
    plugins: [
      react(),
      {
        name: "deployment-bank",
        resolveId(id) {
          if (id === virtualId) return resolvedId;
        },
        load(id) {
          if (id === resolvedId) return `export default Object.freeze(${JSON.stringify(bank)});`;
        },
      },
    ],
    server: {
      port: 5173,
      proxy: {
        // Dev only. In Container Apps nginx proxies /api to the BFF app.
        "/api": { target: "http://localhost:8000", changeOrigin: true },
        "/health": { target: "http://localhost:8000", changeOrigin: true },
      },
    },
  };
});
