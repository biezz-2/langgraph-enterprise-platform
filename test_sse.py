import asyncio
import httpx

async def test_sse():
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Test streaming runs
        thread_id = "73a09596-8068-450d-8755-e35d81c003a4"
        assistant_id = "2a51ad5b-a5d4-490d-8e52-406ed60baac6"
        
        # Create a run with streaming
        response = await client.post(
            "http://localhost:8006/api/runs",
            json={
                "thread_id": thread_id,
                "assistant_id": assistant_id,
                "stream_mode": "values"
            }
        )
        print("Create run (stream_mode=values):", response.status_code, response.json())
        
        # Test stream endpoint
        run_id = response.json()["run_id"]
        print(f"Run ID: {run_id}")
        
        # Test stream with values mode
        print("\nTesting stream mode: values")
        async with client.stream("GET", f"http://localhost:8006/api/runs/{run_id}/stream", params={"stream_mode": "values"}) as resp:
            async for line in resp.aiter_lines():
                print(f"  {line}")
        
        # Test stream with updates mode
        print("\nTesting stream mode: updates")
        async with client.stream("GET", f"http://localhost:8006/api/runs/{run_id}/stream", params={"stream_mode": "updates"}) as resp:
            async for line in resp.aiter_lines():
                print(f"  {line}")

asyncio.run(test_sse())