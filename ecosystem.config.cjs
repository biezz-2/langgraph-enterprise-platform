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
        USE_SUPABASE: "true",
        SUPABASE_URL: "https://supabase-self-hosted.biezz.my.id",
        SUPABASE_SCHEMA: "langgraph",
        SUPABASE_SERVICE_ROLE_KEY: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIiwiaXNzIjoic3VwYWJhc2UiLCJpYXQiOjE3OTE1Mzg3MjcsImV4cCI6MTk0OTIxODcyN30.dgDNAw6lg3JJxCc0owJTsHHUSvb5ybtM_TumaOJ2_Xg",
        SUPABASE_DB_HOST: "127.0.0.1",
        SUPABASE_DB_PORT: "5432",
        SUPABASE_DB_NAME: "postgres",
        SUPABASE_DB_USER: "postgres.your-tenant-id",
        SUPABASE_DB_PASSWORD: "6f8c53668dfb0879dea840fbbc2b3a2e"
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
        MCP_HOST: "0.0.0.0",
        MCP_TRANSPORT: "streamable-http",
        USE_SUPABASE: "true",
        SUPABASE_URL: "https://supabase-self-hosted.biezz.my.id",
        SUPABASE_SCHEMA: "langgraph",
        SUPABASE_SERVICE_ROLE_KEY: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIiwiaXNzIjoic3VwYWJhc2UiLCJpYXQiOjE3OTE1Mzg3MjcsImV4cCI6MTk0OTIxODcyN30.dgDNAw6lg3JJxCc0owJTsHHUSvb5ybtM_TumaOJ2_Xg",
        SUPABASE_DB_HOST: "127.0.0.1",
        SUPABASE_DB_PORT: "5432",
        SUPABASE_DB_NAME: "postgres",
        SUPABASE_DB_USER: "postgres.your-tenant-id",
        SUPABASE_DB_PASSWORD: "6f8c53668dfb0879dea840fbbc2b3a2e"
      }
    },
    {
      name: "lgp-dashboard",
      script: "node_modules/next/dist/bin/next",
      args: "start -p 3000",
      cwd: "/home/biezz/Documents/Project/coding/langgraph/apps/dashboard-nextjs",
      interpreter: "node",
      autorestart: true,
      watch: false,
      max_memory_restart: "500M",
      env: {
        NODE_ENV: "production",
        PORT: "3000"
      }
    }
  ]
};
