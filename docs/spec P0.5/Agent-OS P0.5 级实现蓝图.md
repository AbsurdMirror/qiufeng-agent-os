## **第一章：P0.5 阶段实施原则**

`P0.5` 只做结构整理，不做能力升级。所有阶段都必须遵守以下硬性约束：

- \[ ] 不修改六层现有输入输出协议语义。
- \[ ] 不修改现有运行入口行为语义。
- \[ ] 不重写现有实现，只搬迁文件、重组目录、收口导出、补兼容层。
- \[ ] 目录重组后保留旧路径兼容层，至少覆盖 `P0.5` 全阶段。
- \[ ] `T1-T6` 每完成一个层级改动，立即执行一次 `tests/` 下的全量回归测试。
- \[ ] `T1-T6` 允许调整 `tests/` 内容，但只允许做与目录迁移相关的 import、patch 路径、夹具路径修正，不允许借机放宽断言标准。
- \[ ] 每个 `T` 阶段单独实施、单独复盘、单独回归，不并行混改多个层。

**全量回归基线命令**

```bash
PYTHONPATH=. pytest tests -q
PYTHONPATH=. python -m compileall src
python -m src.app.main --help
```

## ---

**第二章：T1 阶段 —— Channel Gateway 目录重组**

本阶段只重组 `channel_gateway`，不新增渠道、不新增响应原语、不修改飞书链路语义。

### **目录结构**

```text
src/channel_gateway/
  __init__.py
  bootstrap.py
  exports.py
  events.py
  responses.py
  event_parser.py
  feishu_webhook.py
  feishu_long_connection.py
  feishu_sender.py
  session_context.py
  nonebot_runtime.py
  core/
    __init__.py
    nonebot_runtime.py
  domain/
    __init__.py
    events.py
    responses.py
  parsers/
    __init__.py
    text_event_parser.py
  transports/
    __init__.py
    feishu/
      __init__.py
      webhook.py
      long_connection.py
  senders/
    __init__.py
    feishu_async_sender.py
  session/
    __init__.py
    context.py
```

### **具体改动**

- \[ ] 新建 `src/channel_gateway/core/`。
- \[ ] 新建 `src/channel_gateway/domain/`。
- \[ ] 新建 `src/channel_gateway/parsers/`。
- \[ ] 新建 `src/channel_gateway/transports/feishu/`。
- \[ ] 新建 `src/channel_gateway/senders/`。
- \[ ] 新建 `src/channel_gateway/session/`。
- \[ ] 将 `src/channel_gateway/events.py` 的真实实现迁入 `src/channel_gateway/domain/events.py`。
- \[ ] 将 `src/channel_gateway/responses.py` 的真实实现迁入 `src/channel_gateway/domain/responses.py`。
- \[ ] 将 `src/channel_gateway/event_parser.py` 的真实实现迁入 `src/channel_gateway/parsers/text_event_parser.py`。
- \[ ] 将 `src/channel_gateway/feishu_webhook.py` 的真实实现迁入 `src/channel_gateway/transports/feishu/webhook.py`。
- \[ ] 将 `src/channel_gateway/feishu_long_connection.py` 的真实实现迁入 `src/channel_gateway/transports/feishu/long_connection.py`。
- \[ ] 将 `src/channel_gateway/feishu_sender.py` 的真实实现迁入 `src/channel_gateway/senders/feishu_async_sender.py`。
- \[ ] 将 `src/channel_gateway/session_context.py` 的真实实现迁入 `src/channel_gateway/session/context.py`。
- \[ ] 将 `src/channel_gateway/nonebot_runtime.py` 的真实实现迁入 `src/channel_gateway/core/nonebot_runtime.py`。
- \[ ] 保留顶层 `events.py`、`responses.py`、`event_parser.py`、`feishu_webhook.py`、`feishu_long_connection.py`、`feishu_sender.py`、`session_context.py`、`nonebot_runtime.py`，并全部改为兼容 re-export 文件。
- \[ ] 修改 `src/channel_gateway/bootstrap.py`，将内部 import 全部切换到新路径。
- \[ ] 修改 `src/channel_gateway/exports.py`，将类型引用全部切换到新路径。
- \[ ] 修改 `src/channel_gateway/__init__.py`，继续只暴露稳定入口 `initialize`，内部改走新路径。
- \[ ] 修改仓库内部直接依赖旧深路径的源码导入：
  - `src/app/long_connection_runner.py`
  - `src/orchestration_engine/base_orchestrator.py`

### **明确不改**

- \[ ] 不修改 `UniversalEvent`、`UniversalTextEvent`、`ReplyText` 的字段和语义。
- \[ ] 不修改 `FeishuAsyncSender` 的方法名和行为。
- \[ ] 不修改 `SessionContextController` 的逻辑语义。
- \[ ] 不新增 CLI Channel。

### **回归测试**

- \[ ] 运行 `PYTHONPATH=. pytest tests -q`
- \[ ] 若测试因目录迁移失败，修改以下测试的 import 或 monkeypatch 路径：
  - `tests/implement-p0-t1-foundation/tests/test_event_parser.py`
  - `tests/implement-p0-t1-foundation/tests/test_feishu_webhook.py`
  - `tests/T4/tests/test_t4_core.py`
  - `tests/implement-p0-t5-robustness/tests/test_feishu_async_sender.py`
- \[ ] 运行 `PYTHONPATH=. python -m compileall src`
- \[ ] 运行 `python -m src.app.main --help`

## ---

**第三章：T2 阶段 —— Orchestration Engine 目录重组**

本阶段只重组 `orchestration_engine`，不补完整 LangGraph 执行链，不修改 `BaseOrchestrator`、`RuntimeContext`、`Capability` 契约语义。

### **目录结构**

```text
src/orchestration_engine/
  __init__.py
  bootstrap.py
  contracts.py
  agent_registry.py
  base_orchestrator.py
  langgraph_runtime.py
  runtime_context.py
  context_manager.py
  exports.py
  registry/
    __init__.py
    agent_registry.py
  runtime/
    __init__.py
    base_orchestrator.py
    langgraph_runtime.py
  context/
    __init__.py
    runtime_context.py
    state_context_manager.py
  api/
    __init__.py
    exports.py
```

### **具体改动**

- \[ ] 新建 `src/orchestration_engine/registry/`。
- \[ ] 新建 `src/orchestration_engine/runtime/`。
- \[ ] 新建 `src/orchestration_engine/context/`。
- \[ ] 新建 `src/orchestration_engine/api/`。
- \[ ] 将 `src/orchestration_engine/agent_registry.py` 的真实实现迁入 `src/orchestration_engine/registry/agent_registry.py`。
- \[ ] 将 `src/orchestration_engine/base_orchestrator.py` 的真实实现迁入 `src/orchestration_engine/runtime/base_orchestrator.py`。
- \[ ] 将 `src/orchestration_engine/langgraph_runtime.py` 的真实实现迁入 `src/orchestration_engine/runtime/langgraph_runtime.py`。
- \[ ] 将 `src/orchestration_engine/runtime_context.py` 的真实实现迁入 `src/orchestration_engine/context/runtime_context.py`。
- \[ ] 将 `src/orchestration_engine/context_manager.py` 的真实实现迁入 `src/orchestration_engine/context/state_context_manager.py`。
- \[ ] 将 `src/orchestration_engine/exports.py` 的真实实现迁入 `src/orchestration_engine/api/exports.py`。
- \[ ] 保留顶层 `agent_registry.py`、`base_orchestrator.py`、`langgraph_runtime.py`、`runtime_context.py`、`context_manager.py`、`exports.py`，并全部改为兼容 re-export 文件。
- \[ ] 保留 `src/orchestration_engine/contracts.py` 原路径不动。
- \[ ] 修改 `src/orchestration_engine/bootstrap.py`，全部切换到新路径。
- \[ ] 修改 `src/orchestration_engine/__init__.py`，只从新路径聚合导出。
- \[ ] 修改 `src/app/bootstrap.py`，优先从 `src.orchestration_engine` 包级入口取 `initialize` 和 `OrchestrationEngineExports`，不再直接依赖内部文件路径。

### **明确不改**

- \[ ] 不修改 `contracts.py` 文件位置。
- \[ ] 不修改 `BaseOrchestrator.execute()` 语义。
- \[ ] 不修改 `StateContextManager` 的逻辑语义。
- \[ ] 不补真实图执行能力。

### **回归测试**

- \[ ] 运行 `PYTHONPATH=. pytest tests -q`
- \[ ] 若测试因目录迁移失败，修改以下测试和脚本的 import 路径：
  - `tests/implement-p0-t1-foundation/tests/test_agent_registry.py`
  - `tests/implement-p0-t2-skeleton-protocol/tests/test_orchestration_and_observability.py`
  - `tests/implement-p0-t3-capability-access/tests/test_capability_contracts.py`
  - `tests/implement-p0-t3-capability-access/tests/test_capability_hub.py`
  - `tests/implement-p0-t3-capability-access/tests/test_skill_hub.py`
  - `tests/T4/scripts/run_manual_test.py`
- \[ ] 运行 `PYTHONPATH=. python -m compileall src`
- \[ ] 运行 `python -m src.app.main --help`

## ---

**第四章：T3 阶段 —— Skill Hub 目录重组**

本阶段只重组 `skill_hub`，不修改 Capability Hub、Browser Tool、安全原语的行为。

### **目录结构**

```text
src/skill_hub/
  __init__.py
  bootstrap.py
  capability_hub.py
  contracts.py
  tool_parser.py
  exports.py
  security.py
  browser_use.py
  core/
    __init__.py
    capability_hub.py
    contracts.py
    tool_parser.py
    exports.py
  primitives/
    __init__.py
    security.py
  builtin_tools/
    __init__.py
    browser_use.py
```

### **具体改动**

- \[ ] 新建 `src/skill_hub/core/`。
- \[ ] 新建 `src/skill_hub/primitives/`。
- \[ ] 新建 `src/skill_hub/builtin_tools/`。
- \[ ] 将 `src/skill_hub/capability_hub.py` 的真实实现迁入 `src/skill_hub/core/capability_hub.py`。
- \[ ] 将 `src/skill_hub/contracts.py` 的真实实现迁入 `src/skill_hub/core/contracts.py`。
- \[ ] 将 `src/skill_hub/tool_parser.py` 的真实实现迁入 `src/skill_hub/core/tool_parser.py`。
- \[ ] 将 `src/skill_hub/exports.py` 的真实实现迁入 `src/skill_hub/core/exports.py`。
- \[ ] 将 `src/skill_hub/security.py` 的真实实现迁入 `src/skill_hub/primitives/security.py`。
- \[ ] 将 `src/skill_hub/browser_use.py` 的真实实现迁入 `src/skill_hub/builtin_tools/browser_use.py`。
- \[ ] 保留顶层 `capability_hub.py`、`contracts.py`、`tool_parser.py`、`exports.py`、`security.py`、`browser_use.py`，并全部改为兼容 re-export 文件。
- \[ ] 修改 `src/skill_hub/bootstrap.py`，将 import 全部切到新路径。
- \[ ] 修改 `src/skill_hub/__init__.py`，只从新路径聚合导出当前稳定公共对象。
- \[ ] 保留 `src/skill_hub/bootstrap.py` 原路径不变。

### **明确不改**

- \[ ] 不修改 `RegisteredCapabilityHub` 的注册和调用语义。
- \[ ] 不修改 `BrowserUsePyTool` 的 capability id 和输入输出协议。
- \[ ] 不修改 `security.py` 的黑白灰名单、ticket、审批语义。

### **回归测试**

- \[ ] 运行 `PYTHONPATH=. pytest tests -q`
- \[ ] 若测试因目录迁移失败，修改以下测试的 import 或 monkeypatch 路径：
  - `tests/implement-p0-t3-capability-access/tests/test_skill_hub.py`
  - `tests/implement-p0-t3-capability-access/tests/test_capability_hub.py`
  - `tests/implement-p0-t3-capability-access/tests/test_browser_use.py`
  - `tests/implement-p0-t3-capability-access/tests/test_app_bootstrap_task5.py`
  - `tests/implement-p0-t5-robustness/tests/test_security_primitives.py`
  - `tests/T4/tests/test_t4_core.py`
- \[ ] 运行 `PYTHONPATH=. python -m compileall src`
- \[ ] 运行 `python -m src.app.main --help`

## ---

**第五章：T4 阶段 —— Model Provider 目录重组**

本阶段只重组 `model_provider`，不新增 Provider，不改路由策略，不引入对象化模型定义。

### **目录结构**

```text
src/model_provider/
  __init__.py
  bootstrap.py
  contracts.py
  exports.py
  minimax.py
  litellm_adapter.py
  router.py
  schema_validator.py
  providers/
    __init__.py
    minimax.py
    litellm_adapter.py
  routing/
    __init__.py
    router.py
  validators/
    __init__.py
    schema_validator.py
```

### **具体改动**

- \[ ] 新建 `src/model_provider/providers/`。
- \[ ] 新建 `src/model_provider/routing/`。
- \[ ] 新建 `src/model_provider/validators/`。
- \[ ] 将 `src/model_provider/minimax.py` 的真实实现迁入 `src/model_provider/providers/minimax.py`。
- \[ ] 将 `src/model_provider/litellm_adapter.py` 的真实实现迁入 `src/model_provider/providers/litellm_adapter.py`。
- \[ ] 将 `src/model_provider/router.py` 的真实实现迁入 `src/model_provider/routing/router.py`。
- \[ ] 将 `src/model_provider/schema_validator.py` 的真实实现迁入 `src/model_provider/validators/schema_validator.py`。
- \[ ] 保留顶层 `minimax.py`、`litellm_adapter.py`、`router.py`、`schema_validator.py`，并全部改为兼容 re-export 文件。
- \[ ] 保留 `contracts.py`、`bootstrap.py`、`exports.py` 原路径不变。
- \[ ] 修改 `src/model_provider/__init__.py`，只从新路径聚合导出当前稳定公共对象。
- \[ ] 修改 `src/model_provider/bootstrap.py`，全部切到新路径。

### **明确不改**

- \[ ] 不新增新供应商。
- \[ ] 不修改 `ModelRequest`、`ModelResponse`、`ModelProviderClient` 协议语义。
- \[ ] 不修改 `ModelRouter` 的名称匹配和裁剪逻辑语义。
- \[ ] 不修改 `schema_validator` 的校验和自愈行为。

### **回归测试**

- \[ ] 运行 `PYTHONPATH=. pytest tests -q`
- \[ ] 若测试因目录迁移失败，修改以下测试和脚本的 import 路径：
  - `tests/implement-p0-t2-skeleton-protocol/tests/test_model_provider.py`
  - `tests/implement-p0-t3-capability-access/tests/test_minimax.py`
  - `tests/implement-p0-t3-capability-access/tests/test_model_provider_task4.py`
  - `tests/implement-p0-t5-robustness/tests/test_schema_validator.py`
  - `tests/T4/scripts/run_manual_test.py`
- \[ ] 运行 `PYTHONPATH=. python -m compileall src`
- \[ ] 运行 `python -m src.app.main --help`

## ---

**第六章：T5 阶段 —— Storage & Memory 目录重组**

本阶段只重组 `storage_memory`，不新增快照语义，不升级记忆模型，不修改当前 Redis 降级行为。

### **目录结构**

```text
src/storage_memory/
  __init__.py
  bootstrap.py
  exports.py
  contracts.py
  redis_store.py
  contracts/
    __init__.py
    models.py
    protocols.py
  backends/
    __init__.py
    in_memory.py
    redis_store.py
  internal/
    __init__.py
    keys.py
    codecs.py
  factory/
    __init__.py
    create_store.py
```

### **具体改动**

- \[ ] 新建 `src/storage_memory/contracts/`。
- \[ ] 新建 `src/storage_memory/backends/`。
- \[ ] 新建 `src/storage_memory/internal/`。
- \[ ] 新建 `src/storage_memory/factory/`。
- \[ ] 将 `HotMemoryItem` 从 `src/storage_memory/contracts.py` 迁入 `src/storage_memory/contracts/models.py`。
- \[ ] 将 `HotMemoryCarrier`、`StorageAccessProtocol` 从 `src/storage_memory/contracts.py` 迁入 `src/storage_memory/contracts/protocols.py`。
- \[ ] 将 `InMemoryHotMemoryStore` 从 `src/storage_memory/contracts.py` 迁入 `src/storage_memory/backends/in_memory.py`。
- \[ ] 将 `_build_hot_key`、`_build_state_key` 从 `src/storage_memory/contracts.py` 迁入 `src/storage_memory/internal/keys.py`。
- \[ ] 将 `_dump_hot_memory_item`、`_load_hot_memory_item` 从 `src/storage_memory/contracts.py` 迁入 `src/storage_memory/internal/codecs.py`。
- \[ ] 将 `RedisHotMemoryStore` 从 `src/storage_memory/redis_store.py` 迁入 `src/storage_memory/backends/redis_store.py`。
- \[ ] 将 `create_store()` 从 `src/storage_memory/redis_store.py` 迁入 `src/storage_memory/factory/create_store.py`。
- \[ ] 保留顶层 `contracts.py`、`redis_store.py`，并全部改为兼容 re-export 文件。
- \[ ] 修改 `src/storage_memory/bootstrap.py`，将内部 import 全部切到新路径。
- \[ ] 修改 `src/storage_memory/exports.py`，将类型 import 全部切到新路径。
- \[ ] 修改 `src/storage_memory/__init__.py`，继续暴露稳定公共对象。

### **明确不改**

- \[ ] 不修改 `append_hot_memory`、`read_hot_memory`、`persist_runtime_state`、`load_runtime_state` 的行为语义。
- \[ ] 不修改 Redis 不可用时回退到内存存储的语义。
- \[ ] 不新增长期记忆或快照语义。

### **回归测试**

- \[ ] 运行 `PYTHONPATH=. pytest tests -q`
- \[ ] 若测试因目录迁移失败，修改以下测试和脚本的 import 路径：
  - `tests/implement-p0-t2-skeleton-protocol/tests/test_storage_memory.py`
  - `tests/T4/tests/test_t4_core.py`
  - `tests/implement-p0-t3-capability-access/tests/test_app_bootstrap_task5.py`
  - `tests/T4/scripts/run_manual_test.py`
- \[ ] 运行 `PYTHONPATH=. python -m compileall src`
- \[ ] 运行 `python -m src.app.main --help`

## ---

**第七章：T6 阶段 —— Observability Hub 目录重组**

本阶段只重组 `observability_hub`，不新增回放能力，不修改 trace、record、染色、JSONL、CLI tail 的行为。

### **目录结构**

```text
src/observability_hub/
  __init__.py
  bootstrap.py
  recording.py
  request_coloring.py
  jsonl_storage.py
  cli_logger.py
  exports.py
  trace/
    __init__.py
    id_generator.py
  record/
    __init__.py
    recording.py
  coloring/
    __init__.py
    request_coloring.py
  jsonl/
    __init__.py
    storage.py
  cli/
    __init__.py
    tailer.py
  exports/
    __init__.py
    container.py
```

### **具体改动**

- \[ ] 新建 `src/observability_hub/trace/`。
- \[ ] 新建 `src/observability_hub/record/`。
- \[ ] 新建 `src/observability_hub/coloring/`。
- \[ ] 新建 `src/observability_hub/jsonl/`。
- \[ ] 新建 `src/observability_hub/cli/`。
- \[ ] 新建 `src/observability_hub/exports/`。
- \[ ] 将 `GlobalTraceIDGenerator`、`generate_trace_id` 从 `src/observability_hub/recording.py` 迁入 `src/observability_hub/trace/id_generator.py`。
- \[ ] 将 `LogLevel`、`NormalizedRecord`、`record()` 从 `src/observability_hub/recording.py` 迁入 `src/observability_hub/record/recording.py`。
- \[ ] 将 `src/observability_hub/request_coloring.py` 的真实实现迁入 `src/observability_hub/coloring/request_coloring.py`。
- \[ ] 将 `src/observability_hub/jsonl_storage.py` 的真实实现迁入 `src/observability_hub/jsonl/storage.py`。
- \[ ] 将 `src/observability_hub/cli_logger.py` 的真实实现迁入 `src/observability_hub/cli/tailer.py`。
- \[ ] 将 `src/observability_hub/exports.py` 的真实实现迁入 `src/observability_hub/exports/container.py`。
- \[ ] 保留顶层 `recording.py`、`request_coloring.py`、`jsonl_storage.py`、`cli_logger.py`、`exports.py`，并全部改为兼容 re-export 文件。
- \[ ] 修改 `src/observability_hub/bootstrap.py`，将内部 import 全部切到新路径。
- \[ ] 修改 `src/observability_hub/__init__.py`，只从新路径聚合导出当前稳定公共对象。

### **明确不改**

- \[ ] 不修改 `generate_trace_id()`、`record()`、`is_request_colored()` 的语义。
- \[ ] 不修改 JSONL 默认落盘策略。
- \[ ] 不修改 CLI tail 的行为语义。
- \[ ] 不新增新观测后端。

### **回归测试**

- \[ ] 运行 `PYTHONPATH=. pytest tests -q`
- \[ ] 若测试因目录迁移失败，修改以下测试和脚本的 import 或 monkeypatch 路径：
  - `tests/implement-p0-t1-foundation/tests/test_recording.py`
  - `tests/implement-p0-t2-skeleton-protocol/tests/test_orchestration_and_observability.py`
  - `tests/implement-p0-t3-capability-access/tests/test_app_bootstrap_task5.py`
  - `tests/implement-p0-t5-robustness/tests/test_observability_jsonl.py`
  - `tests/implement-p0-t5-robustness/scripts/run_manual_test_agent.py`
- \[ ] 运行 `PYTHONPATH=. python -m compileall src`
- \[ ] 运行 `python -m src.app.main --help`

## ---

**第八章：T7 阶段 —— App 层重组**

本阶段在六层目录重组完成后执行。`app` 负责装配和对外入口收口，但不引入 `P1` 式全新 public API。

### **目录结构**

```text
src/app/
  __init__.py
  bootstrap.py
  facade.py
  main.py
  config.py
  settings_store.py
  feishu_api.py
  long_connection_runner.py
  webhook_server.py
  cli/
    __init__.py
    main.py
    commands.py
  config/
    __init__.py
    runtime.py
    store.py
    feishu_api.py
  runners/
    __init__.py
    long_connection.py
    webhook.py
```

### **具体改动**

- \[ ] 新建 `src/app/cli/`。
- \[ ] 新建 `src/app/config/`。
- \[ ] 新建 `src/app/runners/`。
- \[ ] 新建 `src/app/facade.py`。
- \[ ] 将 `src/app/main.py` 的真实 CLI 实现迁入 `src/app/cli/main.py`。
- \[ ] 新建 `src/app/cli/commands.py`，承接 `main.py` 中的命令执行与交互式配置辅助函数。
- \[ ] 将 `src/app/config.py` 的真实实现迁入 `src/app/config/runtime.py`。
- \[ ] 将 `src/app/settings_store.py` 的真实实现迁入 `src/app/config/store.py`。
- \[ ] 将 `src/app/feishu_api.py` 的真实实现迁入 `src/app/config/feishu_api.py`。
- \[ ] 将 `src/app/long_connection_runner.py` 的真实实现迁入 `src/app/runners/long_connection.py`。
- \[ ] 将 `src/app/webhook_server.py` 的真实实现迁入 `src/app/runners/webhook.py`。
- \[ ] 保留顶层 `main.py`、`config.py`、`settings_store.py`、`feishu_api.py`、`long_connection_runner.py`、`webhook_server.py`，并全部改为兼容 re-export 文件或薄转发入口。
- \[ ] 保留 `src/app/bootstrap.py` 原路径不动。
- \[ ] 在 `src/app/facade.py` 中集中暴露：
  - `build_application`
  - `run_feishu_long_connection`
  - `run_webhook_server`
- \[ ] 修改 `src/app/__init__.py`，只暴露门面级对象与稳定配置入口。

### **明确不改**

- \[ ] 不修改 `build_application()` 的装配语义。
- \[ ] 不修改 `load_config()` 的环境变量与文件合并语义。
- \[ ] 不修改 `config-feishu`、`config-interactive`、`run`、`run-webhook` 的命令行为。
- \[ ] 不删除 `src.app.main` 旧入口。

### **回归测试**

- \[ ] 运行 `PYTHONPATH=. pytest tests -q`
- \[ ] 若测试或脚本因目录迁移失败，修改以下文件的 import 路径：
  - `tests/implement-p0-t3-capability-access/tests/test_app_bootstrap_task5.py`
  - `tests/implement-p0-t1-foundation/scripts/run_manual_test.py`
- \[ ] 运行 `PYTHONPATH=. python -m compileall src`
- \[ ] 运行 `python -m src.app.main --help`

## ---

**第九章：阶段执行顺序**

`P0.5` 的执行顺序固定如下：

1. `T1 Channel Gateway`
2. `T2 Orchestration Engine`
3. `T3 Skill Hub`
4. `T4 Model Provider`
5. `T5 Storage & Memory`
6. `T6 Observability Hub`
7. `T7 App`

每个阶段都单独执行以下闭环：

1. 完成该层目录重组。
2. 修复该层及测试中的导入路径。
3. 跑一次 `tests/` 全量回归。
4. 跑 `compileall` 和 `src.app.main --help`。
5. 记录迁移说明，再进入下一个阶段。
