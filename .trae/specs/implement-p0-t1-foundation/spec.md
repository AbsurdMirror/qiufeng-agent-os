# Agent-OS P0 T1 基础连接与架构落地 Spec

## Why
当前仓库仅有架构与 P0 文档，尚无可执行工程骨架。需要先落地统一目录与代码架构，并实现 P0 的 T1 最小可运行能力，打通“渠道接入-编排注册-监控追踪”基础链路。

## What Changes
- 新建 `src/` 分层目录，按 Channel Gateway / Orchestration Engine / Observability Hub 组织模块。
- 实现 T1 能力：GW-P0-01、GW-P0-02、OE-P0-01、OB-P0-01、OB-P0-03。
- 增加应用启动入口与基础配置，支持 Webhook 入口与本地开发验证。
- 增加最小测试集，覆盖 TraceID 唯一性、record 归一化行为、Agent 注册接口。

## Impact
- Affected specs: 渠道适配层基础接入、编排引擎注册协议、监控中心追踪采集。
- Affected code: `src/channel_gateway/*`、`src/orchestration_engine/*`、`src/observability_hub/*`、`src/app/*`、`tests/*`。

## ADDED Requirements
### Requirement: 分层目录与模块边界
系统 SHALL 提供与架构文档一致的最小目录结构，并明确渠道层、编排层、监控层的职责边界。

#### Scenario: 新工程初始化
- **WHEN** 开发者在仓库中查看源码目录
- **THEN** 能看到按层划分的模块目录与统一入口
- **AND** 每层包含与 T1 对应的最小可运行实现

### Requirement: 飞书 Webhook 文本请求接入
系统 SHALL 提供可挂载的飞书 Webhook 文本接收入口，并对外暴露统一事件对象。

#### Scenario: 接收飞书文本事件
- **WHEN** 飞书向 Webhook 发送文本消息
- **THEN** 网关入口完成请求解析与基本字段提取
- **AND** 生成可继续进入编排流程的标准化输入对象

### Requirement: Agent 注册接口
系统 SHALL 提供支持元数据与身份声明的 Agent 注册能力。

#### Scenario: 注册 Agent
- **WHEN** 上层传入 agent_id、identity、metadata、orchestrator 信息
- **THEN** 注册中心完成校验与存储
- **AND** 返回可查询的注册结果

### Requirement: Trace 与归一化采集
系统 SHALL 提供全局唯一 trace_id 生成能力与统一的 record() 采集接口。

#### Scenario: 记录监控事件
- **WHEN** 任意模块调用 record(trace_id, data, level)
- **THEN** 接口输出统一结构化记录
- **AND** 在输入为 dict / str / BaseModel 类对象时均可处理

## MODIFIED Requirements
### Requirement: P0 T1 实施范围
将“实现 P0 T1”细化为可运行工程骨架、可调用接口与基础测试三部分，确保交付物可验证而非仅文档级描述。

## REMOVED Requirements
### Requirement: 无
**Reason**: 本次为新增实现与结构化落地，不涉及能力下线。
**Migration**: 无。
