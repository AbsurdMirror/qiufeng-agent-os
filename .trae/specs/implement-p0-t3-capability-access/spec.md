# P0 T3 能力接入与转发 Spec

## Why
T1 已完成入口链路与基础底座，T2 已完成协议骨架与跨层契约。进入 T3 后，系统需要真正具备“调用模型”和“调用外部工具”的统一执行能力，否则编排层仍然只能停留在骨架阶段。

## What Changes
- 在编排引擎层新增 Capability 契约、能力发现与统一调用返回协议。
- 新建 Skill Hub 模块，提供最小可用的 PyTools 浏览器能力与系统交互路由。
- 在模型抽象层新增 LiteLLM 归一化适配与 MiniMax 客户端实现，并保持无依赖环境下的优雅降级。
- 在应用启动流程中接入 Skill Hub，并组装可供编排层使用的 Capability Hub。
- 保持现有强类型模块导出与异步边界，不回退 T1/T2 已完成的架构约束。

## Impact
- Affected specs: OE-P0-07, SH-P0-03, SH-P0-04, MP-P0-03, MP-P0-04
- Affected code: `src/orchestration_engine`, `src/skill_hub`, `src/model_provider`, `src/app/bootstrap.py`

## ADDED Requirements
### Requirement: Capability 统一契约
系统 SHALL 提供编排层可消费的 Capability 契约，支持能力元数据发现、按 ID 调用以及统一返回结构。

#### Scenario: 编排层按能力 ID 调用
- **WHEN** 编排器请求某个能力 ID
- **THEN** 系统返回该能力描述，或执行该能力并返回标准结果对象

### Requirement: Skill Hub 浏览器能力
系统 SHALL 提供最小可用的浏览器 PyTools 能力，并通过 Skill Hub 对外暴露统一入口。

#### Scenario: 请求浏览器工具执行
- **WHEN** 上层通过 Capability Hub 调用浏览器工具
- **THEN** Skill Hub 将请求路由到浏览器工具处理器，并返回标准化结果

### Requirement: Capability 转发路由
系统 SHALL 在 Skill Hub 中提供系统交互路由，将模型能力与工具能力统一纳入 Capability 调用路径。

#### Scenario: 转发到不同能力域
- **WHEN** 请求的能力 ID 属于模型域或工具域
- **THEN** 系统将请求转发到对应的模型提供方或 PyTools 实现

### Requirement: LiteLLM 格式归一化
系统 SHALL 提供基于 LiteLLM 的请求归一化适配，将标准 `ModelRequest` 转换为底层供应商调用参数，并将响应回收为统一 `ModelResponse`。

#### Scenario: 归一化模型请求
- **WHEN** 收到统一模型请求对象
- **THEN** 系统可生成 LiteLLM 调用参数，并保持输出字段映射一致

### Requirement: MiniMax 模型适配
系统 SHALL 提供 MiniMax 模型适配实现，允许通过统一模型客户端调用 MiniMax。

#### Scenario: 调用 MiniMax 模型
- **WHEN** 请求指定 MiniMax 模型名称或 MiniMax 路由标识
- **THEN** 系统通过 MiniMax 适配器完成调用，若缺少依赖或配置则返回明确错误或回退状态

## MODIFIED Requirements
### Requirement: 应用模块初始化
应用启动流程 SHALL 在现有强类型模块导出的基础上，新增 Skill Hub 初始化与 Capability Hub 组装，使编排层具备访问模型和工具能力的统一入口。

### Requirement: BaseOrchestrator 能力注入
编排器基类 SHALL 从宽泛的 `Any` 占位升级为明确的 Capability 契约类型，避免后续能力注入继续依赖弱类型。

## REMOVED Requirements
### Requirement: T3 阶段必须完成完整回归测试
**Reason**: 当前任务目标是推进 T3 开发实现，开发角色仅负责代码开发与基础语法检查。
**Migration**: 完成开发后由测试人员和审阅人员接手专项验证与复核。
