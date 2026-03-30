from src.model_provider.contracts import ModelRequest, ModelMessage, InMemoryModelProviderClient
from src.model_provider.router import ModelRouter

router = ModelRouter(clients={"default": InMemoryModelProviderClient(), "test_model": InMemoryModelProviderClient()})

req1 = ModelRequest(messages=(ModelMessage("user", "hi"),), model_name="test_model")
resp1 = router.invoke(req1)
assert resp1.model_name == "test_model"

# Test trimming
system_msg = ModelMessage("system", "You are an assistant.")
msgs = [system_msg]
for i in range(100):
    msgs.append(ModelMessage("user", "Hello this is a test message to fill up context window. " * 50))

req2 = ModelRequest(messages=tuple(msgs), model_name="default")
trimmed_msgs = router._trim_messages(req2.messages, "default")

assert trimmed_msgs[0].role == "system"
assert len(trimmed_msgs) < len(msgs)

print("ModelRouter tests passed!")
