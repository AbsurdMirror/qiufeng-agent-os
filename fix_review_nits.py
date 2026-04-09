import re

# 1. Fix ReplyPrimitive type hinting
with open("src/channel_gateway/responses.py", "r") as f:
    resp_content = f.read()

resp_search = """class ReplyPrimitive(Protocol):
    \"\"\"
    响应原语的基础协议约束 (GW-P0-07-CON-002)。

    用于统一所有响应类型的签名类型提示。
    \"\"\"
    pass"""

resp_replace = """class ReplyPrimitive(Protocol):
    \"\"\"
    响应原语的基础协议约束 (GW-P0-07-CON-002)。

    用于统一所有响应类型的签名类型提示。
    \"\"\"
    content: str"""

resp_content = resp_content.replace(resp_search, resp_replace)
with open("src/channel_gateway/responses.py", "w") as f:
    f.write(resp_content)

# 2. Fix JSON Serialization in feishu_sender.py
with open("src/channel_gateway/feishu_sender.py", "r") as f:
    feishu_content = f.read()

feishu_content = "import json\n" + feishu_content

feishu_search = """        payload = {
            "receive_id": receive_id,
            "receive_id_type": receive_id_type,
            "msg_type": "text",
            "content": '{"text": "' + reply.content.replace('"', '\\\\"') + '"}',
            "reply_to": target_event.message_id
        }"""

feishu_replace = """        payload = {
            "receive_id": receive_id,
            "receive_id_type": receive_id_type,
            "msg_type": "text",
            "content": json.dumps({"text": reply.content}, ensure_ascii=False),
            "reply_to": target_event.message_id
        }"""

feishu_content = feishu_content.replace(feishu_search, feishu_replace)

with open("src/channel_gateway/feishu_sender.py", "w") as f:
    f.write(feishu_content)


# 3. Fix Path Traversal Edge Case in security.py
with open("src/skill_hub/security.py", "r") as f:
    sec_content = f.read()

sec_search = """        target = Path(path).resolve()
        target_str = str(target)

        # Blacklist Checks
        if "/etc/" in target_str or target_str.startswith("/root") or target_str.startswith("/var/run"):
            raise SecurityError(f"Access to sensitive path blocked: {path}")

        # Whitelist Checks
        if target_str.startswith(str(self.workspace)):
            return # Safe to proceed"""

sec_replace = """        target = Path(path).resolve()
        target_str = str(target)

        # Blacklist Checks
        sensitive_dirs = ["/etc", "/root", "/var/run"]
        for s_dir in sensitive_dirs:
            # check if it is or is inside a sensitive dir
            if target_str == s_dir or target_str.startswith(s_dir + "/"):
                raise SecurityError(f"Access to sensitive path blocked: {path}")

        # Whitelist Checks
        # Use is_relative_to to safely prevent sibling directory traversal (e.g. /workspace_malicious)
        if target.is_relative_to(self.workspace):
            return # Safe to proceed"""

sec_content = sec_content.replace(sec_search, sec_replace)

with open("src/skill_hub/security.py", "w") as f:
    f.write(sec_content)
