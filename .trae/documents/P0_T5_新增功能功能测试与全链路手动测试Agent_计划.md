## 摘要

本计划以“代码测试人员”视角，对 P0 蓝图中 T5（系统健壮、安全与调试）的新增能力做功能测试，并补齐一套可覆盖 T1–T5 基本能力的“手动测试 Agent（测试脚本）”，用于你在飞书侧手动验证整体可用性。

约束：仅新增/修改 `tests/` 下的测试脚本与 `docs/AI测试/` 下的测试文档与报告；严禁修改 `src/` 下的业务源码。若发现源码缺陷，仅记录为 Bug。

---

## 当前状态分析（基于仓库现状的可验证事实）

### T5 已实现的关键模块（但未必已串入主链路）

- 渠道层（GW-P0-07/08/09）
  - 纯文本响应原语：`ReplyText`
  - 飞书异步发送器：`FeishuAsyncSender`（httpx.AsyncClient + tenant_access_token TTL 缓存 + 4000 字符分片）
- 工具层（SH-P0-01）
  - 安全原语：TicketStore / create_secure_action / SecureFileSystem / SecureShell / with_security_policy（对 tool 域 capability 自动注入）
- 模型层（MP-P0-05/06/07）
  - Schema 强校验与自愈：`validate_and_heal`（Pydantic + JSON code fence 剥离 + 自愈重试与 fail-fast）
  - 现状：模块在仓库存在，但未发现被主调用链实际引用（属于“可测模块级能力”）
- 观测层（OB-P0-04/05/06）
  - JSONL 调试存储：`JSONLStorageEngine`（写入 + 基于 max_bytes 的轮转）
  - CLI 实时日志：`CLILogTailer`（tail -f + TraceID 过滤 + stop_event 可退出 + 轮转检测）
  - 现状：观测层的 `record()` 目前返回归一化结构，仓库内未见“自动写入 JSONL”的全链路调用点；因此需要在测试 Agent 中显式调用 `write_record()` 来验证 OB-P0-04/05/06 的组合可用性。

### T1–T4 主链路的“可运行入口”与“骨架缺口”

- 飞书长连接可运行入口存在（app runner 会生成 trace_id 并 record），但目前仓库内未看到把 `UniversalEvent` 进一步交给某个 Orchestrator 执行的主调度循环；因此“端到端事件 -> 编排 -> 工具/模型 -> 回复”的闭环，必须通过测试 Agent 在应用外层自行串联实现。

---

## 测试目标与范围

### 测试目标

1. 覆盖 T5 新增能力的功能正确性（单测/组件测试优先，避免依赖真实外网）。
2. 提供一套“手动测试 Agent（测试脚本）”，让你可以在飞书内发送消息驱动测试，完成 T1–T5 基本能力的人工验收。

### 范围内（In Scope）

- T5：GW（ReplyText、FeishuAsyncSender）、SH（安全原语）、MP（Schema 校验与自愈）、OB（JSONL + 轮转 + CLI tail）。
- T1–T4：飞书长连接接入（T1）、UniversalEvent 解析与 SessionContext 去重/身份映射（T2/T4 部分）、CapabilityHub 基本调用（T3）、MiniMax 模型能力（T3/4，可选）。

### 范围外（Out of Scope）

- 修改业务源码以补齐缺失主链路；这将作为缺陷/技术债记录在测试报告中。

---

## 拟交付的测试资产（文件与目录）

### 1) 新增测试目录（spec-name = implement-p0-t5-robustness）

- `tests/implement-p0-t5-robustness/tests/`
  - `test_feishu_async_sender.py`
  - `test_security_primitives.py`
  - `test_schema_validator.py`
  - `test_jsonl_storage_and_cli_logger.py`
- `tests/implement-p0-t5-robustness/scripts/`
  - `run_manual_test_agent.py`（核心：覆盖 T1–T5 的手动测试 Agent）

### 2) 新增测试文档目录

- `docs/AI测试/implement-p0-t5-robustness/`
  - `测试设计文档.md`
  - `测试结果报告_v1.0.0.md`

---

## 详细测试设计（要点级，具体表格在执行阶段落地到“测试设计文档.md”）

### A. 渠道层（T5：GW-P0-07/08/09）

- GW-T5-01 ReplyText 基础约束
  - 输入：空字符串、正常字符串
  - 预期：空内容被拒绝（抛错或构造失败）；正常内容可构造
- GW-T5-02 FeishuAsyncSender 路由选择（群聊 vs 私聊）
  - 输入：target_event.group_id 有值/无值
  - 预期：receive_id_type 分别为 chat_id/open_id，receive_id 选择正确
- GW-T5-03 FeishuAsyncSender 分片发送与 reply_to 规则
  - 输入：>4000 字符内容（mock_mode=True）
  - 预期：分片次数正确；仅第一片带 reply_to；后续片不带；返回值结构符合预期
- GW-T5-04 tenant_access_token TTL 缓存
  - 手段：mock httpx.AsyncClient.post 返回固定 token + expire；多次调用验证缓存命中与过期刷新

### B. 工具层（T5：SH-P0-01）

- SH-T5-01 TicketStore：生成/有效期/consume 核销
- SH-T5-02 create_secure_action：灰名单要求 ticket；带 approved_ticket_id 才执行；执行成功后可核销（由 with_security_policy + CapabilityResult 成功触发）
- SH-T5-03 with_security_policy：异常到 CapabilityResult 的映射
  - REQUIRE_TICKET -> error_code=requires_user_approval + metadata.ticket_id
  - DENY -> error_code=security_policy_violation

### C. 模型层（T5：MP-P0-05/06/07）

- MP-T5-01 去除 ```json 代码块包裹后解析成功
- MP-T5-02 不合法 JSON / Schema 不匹配：healing_func=None 时抛 SchemaValidationError
- MP-T5-03 healing_func 生效：多次修复后成功返回 Pydantic Model
- MP-T5-04 自愈 fail-fast：healing_func 抛出 auth/billing 等关键字异常应直接向上抛出（不吞、不重试到 max）
- MP-T5-05 max_retries 语义：max_total_attempts = max_retries + 1

### D. 观测层（T5：OB-P0-04/05/06）

- OB-T5-01 JSONLStorageEngine.write_record 追加写入一行 JSONL
- OB-T5-02 JSONLStorageEngine 轮转策略（使用小 max_bytes 触发）
  - 预期：debug_trace.jsonl -> .1，历史备份按 backup_count 保留与覆盖
- OB-T5-03 CLILogTailer 按 TraceID 过滤
  - 手段：后台线程 tail；写入多条不同 trace_id；捕获 stdout 验证只输出匹配行
- OB-T5-04 stop_event 生效：tail 可优雅退出（避免僵尸线程）

---

## “全链路手动测试 Agent”设计（覆盖 T1–T5）

### 设计原则

- 不依赖编排层尚未落地的主调度循环：测试 Agent 自行“接事件 -> 生成 trace -> 记录 -> 调模型/工具 -> 发送回复”。
- 对外表现尽量贴近真实产品交互：通过飞书长连接接收消息，并用 FeishuAsyncSender 回传到飞书（覆盖 GW-P0-08/09）。
- 安全原语不修改业务代码：在测试脚本运行时动态注册两个“测试专用 tool capability”，使 with_security_policy 在不改 `src/` 的前提下可被集成验证。

### Agent 行为（建议实现为 run_manual_test_agent.py）

1. 启动方式
   - 主进程：asyncio 事件循环，消费事件队列并并发处理
   - 子进程：spawn 模式运行飞书长连接阻塞 SDK，把 UniversalEvent 投递到 multiprocessing.Queue
2. 每条消息的处理流程
   - 生成 trace_id（OB-P0-01）
   - `record()` 归一化关键数据（OB-P0-03）
   - 将 record 写入 JSONL（OB-P0-04/05）：
     - 测试脚本内部显式调用 `JSONLStorageEngine.write_record()`（弥补当前主链路未接入）
   - 解析指令路由（测试脚本级别的“测试协议”，仅用于验收）：
     - `@agent /model <prompt>`：走 capability_hub 调用 `model.minimax.chat`（如无配置则降级 echo）
     - `@agent /browser-probe`：调用 `tool.browser.open` 且 `probe_only=True`（不真正拉起浏览器，验证 T3 能力与安全拦截）
     - `@agent /shell <cmd>`：调用测试专用 capability `tool.test.shell.exec`
     - `@agent /fs-read <path>`：调用测试专用 capability `tool.test.fs.read_text`
     - `@agent /approve <ticket_id>`：把 ticket_id 缓存为“已批准”，并自动重放上一条被拦截的工具请求（或提示用户重新发送）
   - 将结果用 `FeishuAsyncSender.send_text_reply()` 回传飞书（长回复自动分片）
3. 安全原语验证（手动）
   - 首次执行 `/shell` 或 `/fs-read`：应返回 requires_user_approval，并在回复中提示 ticket_id
   - 发送 `/approve <ticket_id>` 后重试：应放行并返回真实执行结果；同时 ticket 被核销（重复使用应失效）

### 手动验收步骤（写入测试结果报告）

本节将作为《测试结果报告_v1.0.0.md》的“手动验收记录”直接抄入，要求做到：每一步包含【怎么测 / 预期结果 / 覆盖功能点】。

#### 0. 环境准备（前置检查）

- 0.1 飞书侧准备
  - 怎么测：确认已创建飞书自建应用，并把机器人拉入一个群（用于群聊场景）；同时确保你能与机器人发起私聊（用于私聊场景）。
  - 预期结果：群聊和私聊均可向机器人发送文本消息。
  - 覆盖功能点：验证“渠道存在 + 文本事件可触发”，为后续 T1/T5 用例提供输入通道。
- 0.2 本地配置飞书凭证
  - 怎么测：运行项目内的飞书配置 CLI（执行阶段会在报告中记录实际命令与 config_path）。
  - 预期结果：本地配置文件落盘成功；再次运行可读取到配置；缺失字段会被提示。
  - 覆盖功能点：T1（基础通道配置）、配置持久化链路可用性。
- 0.3 可选：配置 MiniMax（用于模型链路）
  - 怎么测：设置环境变量 `QF_MINIMAX_API_KEY`（必需）以及可选的 `QF_MINIMAX_MODEL`、`QF_MINIMAX_BASE_URL`。
  - 预期结果：后续 `/model` 指令能返回非空回复；若未配置则脚本应降级为 echo 并明确提示“模型未配置”。
  - 覆盖功能点：T3/T4（模型能力作为 Capability 的调用路径），以及“缺配置降级”的健壮性（T5 的交付保障理念）。

#### 1. 启动测试 Agent（建立可观测的全链路）

- 1.1 启动脚本
  - 怎么测：在项目根目录运行 `python tests/implement-p0-t5-robustness/scripts/run_manual_test_agent.py`。
  - 预期结果：
    - 控制台提示“长连接已启动/等待消息”；
    - 脚本打印可观测信息：当前进程模式（主进程 asyncio + 子进程长连接）、日志文件路径（默认 `logs/debug_trace.jsonl`）。
  - 覆盖功能点：T1（飞书长连接接入方式可运行）、测试 Agent 的“自串联”能力（弥补编排层主调度缺口）。
- 1.2 启动 CLI tail（建议第二终端）
  - 怎么测：另开一个终端运行 `python -m src.observability_hub.cli_logger --log-file logs/debug_trace.jsonl`（不带 trace_id，先看全量）。
  - 预期结果：CLI 进入 tail 状态；当后续有事件写入 JSONL 时能实时打印；无新日志时不高 CPU 空转。
  - 覆盖功能点：OB-P0-06（CLI 实时日志），并为后续 TraceID 过滤用例做准备。

#### 2. 基础事件闭环（T1 + T5 回传）

- 2.1 私聊最小闭环（接收 -> trace -> record -> JSONL -> 回复）
  - 怎么测：在飞书私聊窗口向机器人发送：`/help`
  - 预期结果：
    - 飞书侧收到机器人回复（纯文本），内容包含：可用指令列表；
    - 回复中包含本次 `trace_id`（用于后续 CLI 过滤）；
    - CLI tail 终端能看到对应 trace_id 的日志输出（至少 1 条：收到消息/解析结果）。
  - 覆盖功能点：
    - T1：飞书文本事件接入（长连接）
    - OB-P0-01/03/04：trace_id 生成、record 归一化、JSONL 落盘（由测试脚本显式写入）
    - GW-P0-07/08/09：ReplyText + 异步回传投递到飞书

- 2.2 群聊最小闭环（群聊路由正确性）
  - 怎么测：在群聊 @ 机器人并发送：`/help`
  - 预期结果：
    - 机器人在群里可见回复（不是“私聊回复你”）；
    - 回复的第一段带“回复某条消息”的语义（如飞书展示 reply_to 效果），后续分片（如果有）不强制要求 reply_to。
  - 覆盖功能点：GW-P0-09（chat_id/open_id 路由切换）、FeishuAsyncSender 的群聊/私聊分发逻辑。

#### 3. 长文本分片（T5：GW-P0-08/09 的鲁棒性）

- 3.1 人工触发超长回复分片
  - 怎么测：发送：`/echo-long 9000`（测试 Agent 约定：生成约 9000 字符的回包）
  - 预期结果：
    - 飞书侧收到多段连续消息（约 3 段：4000/4000/剩余）；
    - 第一段为 reply_to（若在群聊触发），后续段落作为普通消息追加；
    - 不出现“消息发送失败/长度限制”的错误提示。
  - 覆盖功能点：FeishuAsyncSender 的 4000 字符分片策略与 reply_to 规则。

#### 4. 消息去重与身份映射（T4：GW-P0-05/06）

- 4.1 去重：短时间重复触发同一 message_id 不应被重复处理
  - 怎么测：
    - 在飞书里复制同一条消息内容，快速连续发送 2 次：`/echo hi`
    - 观察脚本输出与回复次数（注意：飞书实际会产生不同 message_id；该用例主要验证“脚本内重复投递/网络抖动导致的重复事件”防护是否工作）
  - 预期结果：
    - 若出现重复事件（以脚本日志为准），后一次应被标记为 duplicate 并不再产生二次回复；
    - JSONL 中对 duplicate 应有可观测记录（至少提示“duplicate dropped”）。
  - 覆盖功能点：GW-P0-06（消息去重）、可观测性（重复事件不静默）。

- 4.2 身份映射：同一 open_id 映射到稳定 logical UUID
  - 怎么测：在同一私聊会话连续发送两条：`/whoami`、`/whoami`
  - 预期结果：两次回复中展示的 `logical_uid` 相同（或在日志中一致）。
  - 覆盖功能点：GW-P0-05（身份映射 open_id -> 逻辑 UUID）。

#### 5. 模型能力（T3/T4：模型作为 Capability）

- 5.1 模型成功路径（有 MiniMax 配置）
  - 怎么测：发送：`/model 用一句话总结：T5 的目标是什么？`
  - 预期结果：
    - 飞书侧返回非空自然语言回复；
    - 结果中包含 provider 信息（如脚本打印/日志记录了 provider_id）；
    - CLI tail 可看到“发起模型调用/收到模型结果”的记录。
  - 覆盖功能点：T3/T4（模型能力路由 + 调用）、OB 可观测记录。

- 5.2 模型降级路径（无 MiniMax 配置）
  - 怎么测：清空 `QF_MINIMAX_API_KEY` 后发送：`/model hello`
  - 预期结果：脚本不崩溃；飞书回复明确提示“模型未配置，已降级为 echo”；仍然写入 JSONL。
  - 覆盖功能点：健壮性（T5 交付保障理念）。

#### 6. 工具能力与安全原语（T5：SH-P0-01）

以下用例通过“测试脚本运行时动态注册的 tool capability”来触发 with_security_policy，不修改业务源码。

- 6.1 工具调用触发灰名单（需要授权 ticket）
  - 怎么测：发送：`/shell pwd`
  - 预期结果：
    - 飞书回复：操作被拦截，提示 `requires_user_approval`，并返回 `ticket_id`；
    - CLI tail 中记录本次拦截与 ticket_id（可选）。
  - 覆盖功能点：SH-P0-01（灰名单拦截 + ticket 颁发）、CapabilityResult 的错误码映射。

- 6.2 授权后放行 + 票据核销（防重放）
  - 怎么测：
    1) 在收到 ticket_id 后发送：`/approve <ticket_id>`
    2) 再次发送：`/shell pwd`（或脚本自动重放上一条）
    3) 再发送一次：`/shell pwd --reuse-ticket <ticket_id>`（测试脚本约定：显式携带旧 ticket）
  - 预期结果：
    - 第 2 步放行，返回命令输出（当前工作目录）；
    - 第 3 步旧 ticket 不再有效，应再次要求授权（新的 ticket_id），体现 consume() 核销生效。
  - 覆盖功能点：TicketStore.consume（核销）、安全防重放。

- 6.3 文件系统读取触发授权
  - 怎么测：发送：`/fs-read src/app/main.py`
  - 预期结果：同 6.1/6.2；授权后返回文件前若干行（测试脚本应限制最大输出，避免刷屏）。
  - 覆盖功能点：SecureFileSystem（路径解析/工作目录边界）、灰名单授权流。

- 6.4 异常/边界输入（健壮性）
  - 怎么测：
    - 发送空命令：`/shell` 或 `/shell    `
    - 发送非法路径：`/fs-read ../../../../etc/passwd`（尝试路径穿越）
  - 预期结果：
    - 空命令应被拒绝（DENY 或 requires_user_approval 取决于策略实现，但必须“有明确错误消息”）；
    - 路径穿越必须被阻断或要求授权且日志可观测（最终不得泄露敏感文件内容）。
  - 覆盖功能点：安全策略边界、错误处理不静默。

#### 7. 观测：TraceID 过滤与轮转（T5：OB-P0-04/05/06）

- 7.1 TraceID 精准过滤
  - 怎么测：
    1) 执行任一用例后，从机器人回复中复制 `trace_id`
    2) 另开终端运行：`python -m src.observability_hub.cli_logger --trace-id <trace_id>`
    3) 再触发一次请求（例如 `/help`）
  - 预期结果：CLI 只输出匹配 trace_id 的日志；其他请求不输出。
  - 覆盖功能点：OB-P0-06（过滤逻辑正确）。

- 7.2 轮转可用（小容量触发）
  - 怎么测：发送：`/spam-log 200`（测试 Agent 约定：写入大量 record，确保超过 max_bytes）
  - 预期结果：
    - `logs/debug_trace.jsonl` 被轮转为 `.1/.2...`（以脚本/终端输出与文件存在性为准）；
    - CLI tail 不崩溃，能检测轮转并继续输出新文件内容（stderr 可见 “rotated. Reopening”）。
  - 覆盖功能点：OB-P0-05（滚动清理策略）、OB-P0-06（轮转检测）。

#### 8. 并发与时延（尽量覆盖“异步回传接口”的真实价值）

- 8.1 并发处理验证（不会被单条慢任务阻塞）
  - 怎么测：
    - 发送：`/delay 3 A`、紧接着发送：`/delay 3 B`（测试 Agent 约定：每条请求 await asyncio.sleep(3) 再回复）
  - 预期结果：
    - 两条请求都能被快速“接收并确认处理中”（如果脚本实现了进度回传，则应立即回传“处理中”）；
    - 最终两条回复在约 3 秒后相近时间返回，而不是串行 6 秒。
  - 覆盖功能点：GW-P0-08（异步接口价值）、测试 Agent 的并发消费与任务管理。

---

## 计划执行步骤（实施时序）

1. 生成 `docs/AI测试/implement-p0-t5-robustness/测试设计文档.md`（把上面的要点展开成“测试项表格”，并映射到 specId：GW-P0-07/08/09、SH-P0-01、MP-P0-05/06/07、OB-P0-04/05/06）
2. 在 `tests/implement-p0-t5-robustness/tests/` 实现自动化 pytest 用例
3. 在 `tests/implement-p0-t5-robustness/scripts/` 实现 `run_manual_test_agent.py`
4. 运行自动化测试并记录结果
5. 引导你运行手动测试 Agent 完成飞书侧验收，并记录手动测试结果
6. 输出 `测试结果报告_v1.0.0.md`（包含：环境信息、执行命令、通过/失败、缺陷清单、未接入主链路的风险说明）

---

## 验证与验收（执行阶段的检查清单）

- 自动化：
  - `python -m pytest -q tests/implement-p0-t5-robustness/tests`
- 手动：
  - `python tests/implement-p0-t5-robustness/scripts/run_manual_test_agent.py`
  - 飞书侧按“手动验收步骤”逐条验证
  - `python -m src.observability_hub.cli_logger --trace-id <trace_id>` 验证实时过滤
