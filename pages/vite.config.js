import { defineConfig } from "vite";
export default defineConfig({
  base: "/PhotoJoy/",
  build: { target: "es2022", chunkSizeWarningLimit: 900 },
  worker: { format: "es" },
  server: { host: "127.0.0.1", port: 8770 },
});
