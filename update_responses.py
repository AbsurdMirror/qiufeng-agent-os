import re

with open("src/channel_gateway/responses.py", "r") as f:
    content = f.read()

# Add Protocol import
content = content.replace("from dataclasses import dataclass", "from dataclasses import dataclass\nfrom typing import Protocol")

# Add ReplyPrimitive
primitive_code = """

class ReplyPrimitive(Protocol):
    \"\"\"
    响应原语的基础协议约束 (GW-P0-07-CON-002)。

    用于统一所有响应类型的签名类型提示。
    \"\"\"
    pass
"""
content = content.replace("@dataclass(frozen=True)\nclass ReplyText:", primitive_code + "\n@dataclass(frozen=True)\nclass ReplyText(ReplyPrimitive):")


# Add __post_init__ to ReplyText
post_init_code = """
    def __post_init__(self):
        import logging
        logger = logging.getLogger(__name__)

        if not self.content:
            raise ValueError("ReplyText content cannot be empty.")

        if len(self.content) > 4000:
            logger.warning("ReplyText content exceeds 4000 characters. It will be truncated.")
            # Because it's a frozen dataclass, we must use object.__setattr__
            object.__setattr__(self, 'content', self.content[:4000])
"""

content = content.replace("    content: str", "    content: str\n" + post_init_code)

with open("src/channel_gateway/responses.py", "w") as f:
    f.write(content)
