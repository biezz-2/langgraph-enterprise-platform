import asyncio, json, os
from packages.core.db import get_db_connection

async def main():
    db = await get_db_connection()
    async with db.execute("SELECT checkpoint_id, metadata, checkpoint FROM langgraph.checkpoints WHERE checkpoint->'channel_values'->>'run_id' IS NOT NULL ORDER BY checkpoint_id DESC LIMIT 3") as cur:
        rows = await cur.fetchall()
    for r in rows:
        print("cp:", r["checkpoint_id"])
        print("meta:", r["metadata"])
        cv = r["checkpoint"]
        if isinstance(cv, str): cv = json.loads(cv)
        ch = cv.get("channel_values", {})
        print("cv keys:", list(ch.keys()))
        print("cv sample:", {k: (str(v)[:120]) for k,v in ch.items()})
        print("ts:", cv.get("ts"))
    await db.close()

asyncio.run(main())
