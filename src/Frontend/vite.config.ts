import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": "http://localhost:5000",
    },
  },
  build: {
    // Optimize bundle size
    minify: "terser",
    terserOptions: {
      compress: {
        drop_console: true,
        drop_debugger: true,
      },
    },
    // Enable code splitting for better caching
    rollupOptions: {
      output: {
        manualChunks: {
          // Split vendor libraries
          reactFlow: ["@xyflow/react"],
          radix: ["@radix-ui/react-accordion", "@radix-ui/react-dialog", "@radix-ui/react-dropdown-menu"],
          charts: ["recharts"],
          router: ["react-router"],
          ui: ["sonner", "clsx", "class-variance-authority"],
        },
      },
    },
    // Reduce CSS in JS
    cssCodeSplit: true,
    // Optimize source maps for production
    sourcemap: "hidden",
    // Chunk size warnings
    chunkSizeWarningLimit: 500,
    // Report compressed size
    reportCompressedSize: true,
  },
  // Optimize dependencies
  optimizeDeps: {
    include: [
      "react",
      "react-dom",
      "@xyflow/react",
      "recharts",
      "react-router",
    ],
  },
});
