import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: "jsdom",
    css: false,
    setupFiles: ["./tests/setup.js"],
    server: { deps: { inline: ["vuetify"] } },
  },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
