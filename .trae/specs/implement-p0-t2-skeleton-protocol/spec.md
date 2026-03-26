# P0 T2 骨架协议实现 Spec

## Why
当前项目已完成 P0 T1 的接入与基础能力，但尚未建立跨层协议骨架。为进入后续 T3/T4，需要先完成 T2 的统一事件结构、编排执行基类、模型接口适配、热记忆协议与请求染色能力。

## What Changes
- 实现渠道层 UniversalEvent 结构与飞书消息到 UniversalEvent 的标准映射。
- 在编排层新增 BaseOrchestrator 抽象基类，并补齐 LangGraph 运行时骨架接口。
- 新建模型抽象层最小接口适配模块，提供与编排层交互的同步调用契约。
- 新建存储与记忆层最小热记忆载体与存取协议接口（Redis 风格抽象 + 内存回退实现）。
- 在监控中心新增请求染色判定能力（OB-P0-02），并暴露到应用上下文。
- 保持现有长连接链路可用，不回退用户已修改代码。

## Impact
- Affected specs: GW-P0-03, GW-P0-04, OE-P0-02, OE-P0-03, MP-P0-08, SM-P0-01, SM-P0-05, OB-P0-02
- Affected code: `src/channel_gateway`, `src/orchestration_engine`, `src/model_provider`, `src/storage_memory`, `src/observability_hub`, `src/app/bootstrap.py`

## ADDED Requirements
### Requirement: UniversalEvent 协议骨架
系统 SHALL 提供与渠道无关的 `UniversalEvent` 数据结构，并支持从飞书事件映射生成。

#### Scenario: 飞书文本事件映射成功
- **WHEN** 接收到飞书长连接或 Webhook 文本消息
- **THEN** 系统生成字段完整、结构统一的 `UniversalEvent`

### Requirement: 编排执行骨架
系统 SHALL 提供 `BaseOrchestrator` 抽象接口与 LangGraph 运行时加载骨架，供后续编排策略接入。

#### Scenario: 编排实现可按统一签名执行
- **WHEN** 新编排器继承 `BaseOrchestrator`
- **THEN** 编排器可接收 `UniversalEvent`、`RuntimeContext` 与能力代理并返回标准结果

### Requirement: 模型接口适配
系统 SHALL 提供模型层到编排层的最小同步交互契约（MP-P0-08）。

#### Scenario: 编排层发起模型调用
- **WHEN** 编排层通过模型接口调用推理
- **THEN** 模型适配层返回统一响应对象，不暴露供应商差异

### Requirement: 热记忆载体与存取协议
系统 SHALL 提供热记忆抽象存储接口及标准存取协议，支持 RuntimeContext 的读写。

#### Scenario: 运行时状态写入与读取
- **WHEN** 编排层写入或读取热记忆
- **THEN** 通过统一协议完成操作，并可在无 Redis 依赖时使用内存回退实现

### Requirement: 请求染色机制
系统 SHALL 提供请求染色判定能力并向上层导出。

#### Scenario: 请求进入时判定染色
- **WHEN** 入口接收请求上下文
- **THEN** 可得到是否全量采集的布尔判定结果

## MODIFIED Requirements
### Requirement: 应用模块导出与初始化
应用启动流程 SHALL 在现有强类型导出的基础上，新增模型层与存储层的 T2 初始化接入，并继续兼容当前运行命令。

## REMOVED Requirements
### Requirement: T2 阶段内必须完成自动化测试
**Reason**: 当前任务要求“只实现代码开发，不需要测试”。
**Migration**: 测试工作由独立测试角色在后续流程执行，本次仅保证代码结构可编译与可接入。
