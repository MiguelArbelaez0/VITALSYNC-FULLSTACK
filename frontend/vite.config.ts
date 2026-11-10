import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: { "/api": process.env.VITALSYNC_API_TARGET ?? "http://localhost:8088" } },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.tsx"],
    restoreMocks: true,
  },
});
