import asyncio, json
from packages.core.db import get_db_connection

async def main():
    db = await get_db_connection()
    async with db.execute("SELECT event_type, subagent_id, COUNT(*) c FROM telemetry_events GROUP BY 1,2 ORDER BY 1,2") as cur:
        for r in await cur.fetchall():
            print(dict(r))
    await db.close()

asyncio.run(main())
