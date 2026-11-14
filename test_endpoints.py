import asyncio
from fastapi.testclient import TestClient
from apps.api.main import app

client = TestClient(app)

# Test health endpoint
print("Health:", client.get("/api/health").json())

# Test assistants search
print("Assistants search:", client.post("/api/assistants/search", json={"limit": 10}).json())

# Test create assistant
print("Create assistant:", client.post("/api/assistants", json={"graph_id": "test_graph", "name": "Test Assistant"}).json())

# Test threads search
print("Threads search:", client.post("/api/threads/search", json={"limit": 10}).json())

# Test create thread
print("Create thread:", client.post("/api/threads", json={"metadata": {"test": "value"}}).json())

# Test runs search
print("Runs search:", client.post("/api/runs/search", json={"limit": 10}).json())

# Test create run
thread_id = "73a09596-8068-450d-8755-e35d81c003a4"
assistant_id = "2a51ad5b-a5d4-490d-8e52-406ed60baac6"
print("Create run:", client.post("/api/runs", json={"thread_id": thread_id, "assistant_id": assistant_id}).json())

# Test store search
print("Store search:", client.post("/api/store/items/search", json={"limit": 10}).json())

# Test put store item
print("Put store item:", client.put("/api/store/items", json={"namespace": ["test", "ns2"], "key": "key2", "value": {"data": "value2"}}).json())

# Test get store item
print("Get store item:", client.get("/api/store/items", params={"namespace": ["test", "ns2"], "key": "key2"}).json())

# Test list store namespaces
print("List store namespaces:", client.post("/api/store/namespaces", json={"limit": 10}).json())