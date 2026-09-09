import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "/static/", // FastAPI 挂载在 /static,资源必须走这个前缀
  build: {
    outDir: "../static", // 直接产出到 FastAPI 的 static 目录
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    // 本地开发:前端 5173,API 转发到 8000
    proxy: {
      "/auth": "http://localhost:8000",
      "/chats": "http://localhost:8000",
      "/tasks": "http://localhost:8000",
    },
  },
});
