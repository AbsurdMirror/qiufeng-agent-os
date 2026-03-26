from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class AgentIdentity:
    """Agent 的核心身份标识，联合决定一个唯一的 Agent 版本"""
    agent_id: str
    version: str
    tenant_id: str


@dataclass(frozen=True)
class AgentOrchestrator:
    """
    Agent 的编排驱动配置。
    engine_type: 驱动引擎类型（例如 "langgraph", "langchain", "custom"）
    entrypoint: 图执行的入口节点或起始函数路径
    """
    engine_type: str
    entrypoint: str


@dataclass(frozen=True)
class AgentCapabilityMap:
    """Agent 所绑定的能力映射，决定其在运行时能调用哪些模型和工具"""
    model_ids: tuple[str, ...]
    skill_ids: tuple[str, ...]


@dataclass(frozen=True)
class AgentSpec:
    """
    完整的 Agent 规格描述书 (Specification)。
    这是整个编排引擎运转的元数据基石。
    """
    identity: AgentIdentity
    metadata: dict[str, Any]
    orchestrator: AgentOrchestrator
    capability_map: AgentCapabilityMap
    config: dict[str, Any]


class AgentRegistry(Protocol):
    """
    Agent 注册中心的抽象接口协议 (Duck Typing)。
    遵循依赖倒置原则，上层应用只依赖此协议，不关心底层是内存、Redis 还是 DB 存储。
    """
    def register(self, spec: AgentSpec) -> AgentSpec: ...

    def get(
        self,
        agent_id: str,
        tenant_id: str,
        version: str | None = None,
    ) -> AgentSpec | None: ...

    def list_all(self) -> list[AgentSpec]: ...

    def list_by_tenant(self, tenant_id: str) -> list[AgentSpec]: ...


class InMemoryAgentRegistry:
    """
    基于内存字典实现的本地 Agent 注册中心。
    主要用于 P0 阶段的基础跑通和单机测试。
    """
    def __init__(self) -> None:
        # key 格式为: (tenant_id, agent_id, version)
        self._records: dict[tuple[str, str, str], AgentSpec] = {}

    def register(self, spec: AgentSpec) -> AgentSpec:
        """注册一个新的 Agent 规格到内存中"""
        _validate_agent_spec(spec)
        key = self._build_key(
            agent_id=spec.identity.agent_id,
            tenant_id=spec.identity.tenant_id,
            version=spec.identity.version,
        )
        self._records[key] = spec
        return spec

    def get(
        self,
        agent_id: str,
        tenant_id: str,
        version: str | None = None,
    ) -> AgentSpec | None:
        """
        获取 Agent 规格。
        如果指定了 version，则精确匹配。
        如果未指定 version (None)，则通过倒序排序自动返回该 Agent 的最新版本。
        """
        if version is not None:
            key = self._build_key(agent_id=agent_id, tenant_id=tenant_id, version=version)
            return self._records.get(key)

        matches = [
            spec
            for spec in self._records.values()
            if spec.identity.agent_id == agent_id and spec.identity.tenant_id == tenant_id
        ]
        if not matches:
            return None
        # 根据版本号进行字典序降序排列，取第一个即为最新版本
        return sorted(matches, key=lambda item: item.identity.version, reverse=True)[0]

    def list_all(self) -> list[AgentSpec]:
        return list(self._records.values())

    def list_by_tenant(self, tenant_id: str) -> list[AgentSpec]:
        return [spec for spec in self._records.values() if spec.identity.tenant_id == tenant_id]

    def _build_key(self, agent_id: str, tenant_id: str, version: str) -> tuple[str, str, str]:
        return tenant_id, agent_id, version


def _validate_agent_spec(spec: AgentSpec) -> None:
    """注册前置校验：确保核心字段不为空"""
    if not spec.identity.agent_id.strip():
        raise ValueError("invalid_agent_id")
    if not spec.identity.version.strip():
        raise ValueError("invalid_version")
    if not spec.identity.tenant_id.strip():
        raise ValueError("invalid_tenant_id")
    if not spec.orchestrator.engine_type.strip():
        raise ValueError("invalid_engine_type")
    if not spec.orchestrator.entrypoint.strip():
        raise ValueError("invalid_entrypoint")

