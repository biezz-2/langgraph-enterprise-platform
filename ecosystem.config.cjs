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
        PORT: "8000"
      }
    }
  ]
};
