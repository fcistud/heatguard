import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Production/Docker: dashboard is served at /dashboard/ behind the same host as the API.
// Local `npm run dev` also uses this base — open http://localhost:5173/dashboard/
export default defineConfig({
  base: "/dashboard/",
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 700,
    rolldownOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules/recharts")) return "charts";
          if (
            id.includes("node_modules/react") ||
            id.includes("node_modules/react-dom") ||
            id.includes("node_modules/scheduler")
          ) {
            return "react";
          }
          return undefined;
        },
      },
    },
  },
});
