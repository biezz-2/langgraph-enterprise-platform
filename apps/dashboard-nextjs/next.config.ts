import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  experimental: {
    agentUpgrade: "security",
  },
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8000/api/:path*",
      },
      {
        source: "/mcp/admin/:path*",
        destination: "http://localhost:8000/mcp/admin/:path*",
      },
      {
        source: "/docs",
        destination: "http://localhost:8000/docs",
      },
      {
        source: "/openapi.json",
        destination: "http://localhost:8000/openapi.json",
      },
    ];
  },
};

export default nextConfig;
