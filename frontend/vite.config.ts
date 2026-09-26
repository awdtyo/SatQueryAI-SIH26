import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        // Keeps each vendor slice under the 500 kB minified warning threshold.
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (/node_modules\/(recharts|d3-|victory-)/.test(id)) return "charts";
          if (/node_modules\/(react-markdown|remark-|micromark|mdast-)/.test(id)) return "markdown";
          if (/node_modules\/(react|react-dom|scheduler)\//.test(id)) return "react";
          return "vendor";
        },
      },
    },
  },
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
