import time
from src.channel_gateway.session_context import SessionContextController

controller = SessionContextController(deduplication_window_ms=1000)

uuid1 = controller.get_logical_uuid("user_abc")
uuid2 = controller.get_logical_uuid("user_abc")
assert uuid1 == uuid2
assert controller.get_logical_uuid("user_xyz") != uuid1

assert not controller.is_duplicate("msg_1")
assert controller.is_duplicate("msg_1")
assert not controller.is_duplicate("msg_2")

time.sleep(1.1)
assert not controller.is_duplicate("msg_1")

print("SessionContextController tests passed!")
