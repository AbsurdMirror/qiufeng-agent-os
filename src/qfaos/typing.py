from typing import Annotated

from pydantic import Field

# 定义常用的业务 ID 类型，利用 Annotated 补充元数据描述
SessionId = Annotated[str, Field(description="全局唯一的会话 ID")]
UserId = Annotated[str, Field(description="用户标识 ID")]
TraceId = Annotated[str, Field(description="全链路追踪 ID")]
