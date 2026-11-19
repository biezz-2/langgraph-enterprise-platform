// Secrets dimuat dari .env (gitignored) — JANGAN tulis credential langsung di file ini.
const fs = require("fs");
const path = require("path");

const envFile = path.join(__dirname, ".env");
const fileEnv = {};
if (fs.existsSync(envFile)) {
  for (const line of fs.readFileSync(envFile, "utf8").split("\n")) {
    const m = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$/);
    if (m && !line.trim().startsWith("#")) {
      fileEnv[m[1]] = m[2].replace(/^["']|["']$/g, "");
    }
  }
}
const secret = (key) => fileEnv[key] || process.env[key] || "";

const supabaseEnv = {
  USE_SUPABASE: "true",
  SUPABASE_URL: "https://supabase-self-hosted.biezz.my.id",
  SUPABASE_SCHEMA: "langgraph",
  SUPABASE_SERVICE_ROLE_KEY: secret("SUPABASE_SERVICE_ROLE_KEY"),
  SUPABASE_DB_HOST: "127.0.0.1",
  SUPABASE_DB_PORT: "5432",
  SUPABASE_DB_NAME: "postgres",
  SUPABASE_DB_USER: secret("SUPABASE_DB_USER") || "postgres.your-tenant-id",
  SUPABASE_DB_PASSWORD: secret("SUPABASE_DB_PASSWORD"),
};

module.exports = {
  apps: [
    {
      name: "lgp-api",
      script: "/home/biezz/Documents/Project/coding/langgraph/.venv/bin/uvicorn",
      args: "apps.api.main:app --host 0.0.0.0 --port 8000",
      cwd: "/home/biezz/Documents/Project/coding/langgraph",
      interpreter: "none",
      autorestart: true,
      watch: false,
      max_memory_restart: "500M",
      env: {
        PYTHONPATH: "/home/biezz/Documents/Project/coding/langgraph",
        LGP_DB_PATH: "/home/biezz/Documents/Project/coding/langgraph/data/lgp.db",
        PORT: "8000",
        ROUTER_BASE_URL: "https://9router.biezz.my.id/v1",
        ROUTER_API_KEY: secret("ROUTER_API_KEY"),
        ...supabaseEnv,
      }
    },
    {
      name: "lgp-mcp",
      script: "/home/biezz/Documents/Project/coding/langgraph/.venv/bin/python",
      args: "-m apps.admin_mcp.mcp_server_cli --transport streamable-http --host 0.0.0.0 --port 8787",
      cwd: "/home/biezz/Documents/Project/coding/langgraph",
      interpreter: "none",
      autorestart: true,
      watch: false,
      max_memory_restart: "500M",
      env: {
        PYTHONPATH: "/home/biezz/Documents/Project/coding/langgraph",
        LGP_DB_PATH: "/home/biezz/Documents/Project/coding/langgraph/data/lgp.db",
        MCP_PORT: "8787",
        ROUTER_BASE_URL: "https://9router.biezz.my.id/v1",
        ROUTER_API_KEY: secret("ROUTER_API_KEY"),
        MCP_HOST: "0.0.0.0",
        MCP_TRANSPORT: "streamable-http",
        ...supabaseEnv,
      }
    },
    {
      name: "lgp-dashboard",
      script: "node_modules/next/dist/bin/next",
      args: "start -p 3002",
      cwd: "/home/biezz/Documents/Project/coding/langgraph/apps/dashboard-nextjs",
      interpreter: "node",
      autorestart: true,
      watch: false,
      max_memory_restart: "500M",
      env: {
        NODE_ENV: "production",
        PORT: "3002"
      }
    }
  ]
};
