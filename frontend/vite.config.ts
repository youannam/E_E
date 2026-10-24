import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dashboard talks to the FastAPI backend at VITE_API_BASE_URL (see .env.example).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  preview: { port: 4173 },
});
