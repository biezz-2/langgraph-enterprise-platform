import asyncio
from langgraph_sdk import get_client

async def test():
    client = get_client(url="http://localhost:8006/api")
    
    # Test assistants
    assistants = await client.assistants.search(limit=10)
    print("Assistants search:", assistants)
    
    # Test threads
    threads = await client.threads.search(limit=10)
    print("Threads search:", threads)
    
    # Test runs - SDK uses list with thread_id
    thread_id = "73a09596-8068-450d-8755-e35d81c003a4"
    runs = await client.runs.list(thread_id=thread_id, limit=10)
    print("Runs list:", runs)
    
    # Test store
    # Note: langgraph_sdk may not have store endpoints

asyncio.run(test())