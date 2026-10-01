import { defineConfig } from "vite";
import { bundledInventory } from "./host/bundledInventory.mjs";

export default defineConfig({
  base: "./",
  plugins: [bundledInventory()],
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
