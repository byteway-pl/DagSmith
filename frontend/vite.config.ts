/// <reference types="vitest/config" />
import { resolve } from "node:path";

import react from "@vitejs/plugin-react-swc";
import { defineConfig } from "vite";
import cssInjectedByJsPlugin from "vite-plugin-css-injected-by-js";

// Library build contract required by Airflow's react_apps loader (AIP-68):
// a UMD bundle exposing the plugin component as `globalThis.AirflowPlugin`,
// with react/react-dom/react-router-dom provided as globals by the host UI.
export default defineConfig(({ command }) => {
  const isLibraryBuild = command === "build";

  return {
    base: "./",
    build: isLibraryBuild
      ? {
          chunkSizeWarningLimit: 1600,
          // The packaged bundle is served by the plugin's FastAPI app at /dagsmith/ui/.
          outDir: resolve("..", "src", "dagsmith", "static"),
          emptyOutDir: false,
          lib: {
            entry: resolve("src", "main.tsx"),
            fileName: () => "dagsmith.js",
            formats: ["umd"],
            name: "AirflowPlugin",
          },
          rollupOptions: {
            external: ["react", "react-dom", "react-router-dom", "react/jsx-runtime"],
            output: {
              globals: {
                react: "React",
                "react-dom": "ReactDOM",
                "react-router-dom": "ReactRouterDOM",
                "react/jsx-runtime": "ReactJSXRuntime",
              },
            },
          },
        }
      : {
          chunkSizeWarningLimit: 1600,
        },
    define: {
      global: "globalThis",
      "process.env": "{}",
      "process.env.NODE_ENV": JSON.stringify("production"),
    },
    plugins: [react(), cssInjectedByJsPlugin()],
    resolve: { alias: { src: resolve("src") } },
    server: {
      cors: true,
    },
    test: {
      environment: "happy-dom",
      include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    },
  };
});
