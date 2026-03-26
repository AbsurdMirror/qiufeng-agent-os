# 审阅报告：implement-p0-t1-foundation

## P0 级建议与结论（核心阻断/架构级调整）
* [x] **强类型模块导出重构**：当前各层的 `bootstrap.py`（如 `channel_gateway`, `observability_hub`）使用 `dict[str, Any]` 暴露接口，这彻底破坏了 IDE 的代码跳转（Go to Definition）和静态类型检查（mypy）。必须将返回类型重构为具体的强类型 `Dataclass`（例如 `ObservabilityHubExports`），这是保障后续大型系统开发可维护性的核心基石。
* [x] **配置加载机制重构**：当前仅飞书配置支持本地文件持久化，且加载优先级为环境变量覆盖文件。需重构为：所有配置参数（含基础网络、环境变量等）均支持本地配置文件持久化，并且**配置文件优先级高于环境变量**（配置文件可覆盖环境变量）。
* [x] **新增交互式配置 CLI**：摒弃现有的长参数传递方式，开发一套可交互的 CLI 命令。用户可通过上下键和回车键选择配置项或配置组；对于枚举值支持上下键选择，字符串则支持终端输入。
* [x] **异步/并发运行架构的早期引入 (防范全局重构风险)**：当前 `run_feishu_long_connection` 会完全阻塞主线程。虽然在 T1~T4 阶段能勉强跑通同步链路，但考虑到 Python `asyncio` 具有**“病毒式传染性”**（一旦底层异步，上层所有调用链都必须改为 `async/await`），如果拖到 T5 阶段再改造，将面临**修改范围波及全层级（网关、编排、模型、存储全部需要重构）**的巨大风险。因此，**强烈建议在 T2 阶段（骨架协议层）就确立异步底座**，将当前的回调和接口全面升级为异步协程（Coroutine）。

## P1 级建议与结论（重要功能/体验优化）
* [x] **领域模型解耦与重构**：当前统一事件模型 `UniversalTextEvent` 定义在 `feishu_webhook.py` 中，存在领域模型与特定渠道实现耦合的问题。需将其抽离到独立的模型文件中（如 `src/channel_gateway/models.py` 或抽象的 `events.py`）。
* [x] **引入事件解析工厂模式**：鉴于未来需接入多种渠道（钉钉、微信等）且各渠道原始参数格式不一致，应重构当前的解析逻辑。为 `UniversalTextEvent` 提供工厂方法或独立的解析策略类（Strategy Pattern），针对不同渠道实现专门的 `parse_from_xxx` 构造函数。

## P2 级建议与结论（边缘优化/代码规范）
* [x] `src/observability_hub/recording.py` 缺乏注释，已完成 Docstrings 和内部逻辑注释的补充。
* [x] `src/app/bootstrap.py` 与 `src/app/config.py` 缺乏关键逻辑注释，已完成补充。
* [x] 误创建的嵌套目录 `home/dongzhengxiang/...` 虽然未被引用，但属于脏数据，已由人工手动清理。