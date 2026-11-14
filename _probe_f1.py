import asyncio, json
from packages.core.db import get_db_connection

async def main():
    db = await get_db_connection()
    try:
        async with db.execute(
            "SELECT checkpoint_id, checkpoint->'channel_values'->>'run_id' AS run_id, "
            "metadata->>'step' AS step, checkpoint->>'ts' AS ts, "
            "checkpoint->'channel_values'->>'current_subagent' AS node, "
            "checkpoint->'channel_values' AS cv "
            "FROM langgraph.checkpoints "
            "WHERE checkpoint->'channel_values'->>'run_id' IS NOT NULL "
            "ORDER BY checkpoint_id DESC LIMIT 3"
        ) as cur:
            rows = await cur.fetchall()
        for r in rows:
            print({k: (type(v).__name__, str(v)[:120]) for k, v in dict(r).items()})
    finally:
        await db.close()

asyncio.run(main())
