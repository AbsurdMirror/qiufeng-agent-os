# T5 系统健壮、安全与调试 —— 代码审阅报告

**对应提交**：`b6a70a4b97505197f3aa9c3c375b6b09ca5d6162`
**对应规格**：P0 T5 阶段（GW-P0-07/08/09、SH-P0-01、MP-P0-05/06/07、OB-P0-04/05/06）

---

## 审阅进度列表

- [x] `src/channel_gateway/responses.py` — GW-P0-07 响应原语
- [x] `src/channel_gateway/feishu_sender.py` — GW-P0-08 & GW-P0-09 飞书异步接口
- [x] `src/model_provider/schema_validator.py` — MP-P0-05/06/07 Pydantic 校验与自愈
- [x] `src/skill_hub/security.py` — SH-P0-01 安全原语
- [x] `src/skill_hub/capability_hub.py` — 安全原语集成（修改）
- [x] `src/observability_hub/cli_logger.py` — OB-P0-06 CLI 实时日志
- [x] `src/observability_hub/jsonl_storage.py` — OB-P0-04/05 JSONL 存储引擎
- [x] `src/observability_hub/exports.py` — OB 导出扩展（修改）

### 第二次审阅 (Commit `1ecfdcc18b5be5ff36689939c61878887c1508b2`)

- [x] `src/channel_gateway/responses.py`
- [x] `src/channel_gateway/feishu_sender.py`
- [x] `src/model_provider/schema_validator.py`
- [x] `src/skill_hub/security.py`
- [x] `src/skill_hub/capability_hub.py`
- [x] `src/observability_hub/jsonl_storage.py`
- [x] `src/observability_hub/cli_logger.py`
- [x] `src/observability_hub/bootstrap.py`

---

## P0 级建议与结论（核心阻断/架构级调整）

- [ ] **[REV-VAL-CON-001]（二次审阅新增）** `schema_validator.py` 第 129 行：`AutoHealingMaxRetriesExceeded` 直接包裹了底层 `heal_err` 但缺乏错误详情的现场捕捉。若遭遇高频异常限流等情况在日志层面发生“内层追踪黑洞”，建议在异常上抛前补充 `logger.error` 配合 `exc_info=True` 留存现场痕迹。

- [ ] **[REV-VAL-RISK-001]（二次审阅新增）** `schema_validator.py` 第 100-135 行（整个自愈大循环）：对于因大模型账号欠费缺额度（Rates Limit/401）或网络完全失效诱发的报错，当前结构缺乏**致命错误甄别器 (Fail-fast Checker)**。遇到这些绝对不可自愈的拦路虎时依然会闭着眼睛盲目循环填满 `max_retries`。建议在 `except Exception as heal_err:` 内部加装对异常特征判定，提供直接 `break` 或抛出中止的止损能力。

- [ ] **[REV-SEC-CON-001]（二次审阅新增）** `security.py` 第 42 行：基于内存 `set` 的 `TicketStore` 缺乏过期回收与垃圾清理机制。一旦长时间运行积攒了大量发往前端但被用户忽略（未消费结单）的授权凭单，会导致服务发生内存泄露（OOM）。建议：修改 `TicketStore` 的构造函数使其支持传递 `timeout`（超时时间）参数，对于非 `None` 的配置项基于时间戳或后台清理任务剔除过期失效。

- [x] **[REV-GW07-CON-001]** `responses.py`：`ReplyText.content` 字段没有非空校验，`ReplyText(content="")` 合法，会向用户发出空白消息。应在 `__post_init__` 中添加非空检查，拒绝构造空内容的响应原语。

- [x] **[REV-GW07-BUG-001]** `responses.py`：`ReplyText.content` 没有长度上限校验。飞书平台单条文本消息上限为 **4000 字符**，超出时飞书 API 会报错且调用方无感知，导致消息静默丢失。应在 `__post_init__` 或发送器中添加长度截断/拦截逻辑。

- [x] **[REV-GW0809-CON-002+BUG-001]** `feishu_sender.py`：当前 `send_text_reply` 缺少对**真实飞书 API** 的完整支持，存在两处必须在接入前修复的问题：
  1. **群聊路由缺失**：`receive_id` 硬编码为 `target_event.user_id`，群聊场景下消息会发给个人而非群组，应根据 `target_event.group_id` 是否存在动态切换。
  2. **缺少必填字段**：飞书开放平台 API 要求同时传入 `receive_id_type`（如 `"open_id"` / `"chat_id"`），当前 payload 完全缺失此字段，切换真实模式后所有消息必然发送失败。

- [x] **[REV-MP050607-CON-001]** `schema_validator.py`：`max_retries` 参数语义歧义——当前 `while attempts < max_retries` 的逻辑使得参数含义为"总尝试次数（含第一次）"，而非调用方直觉上的"额外重试次数"。传入 `max_retries=3` 时，`healing_func` 实际只会被调用 **2 次**。应将循环条件改为 `while attempts < max_retries + 1`，使 `max_retries` 的语义准确对应"额外重试次数"。

- [x] **[REV-MP050607-BUG-001]** `schema_validator.py` 第 38 行：markdown 代码块剥离逻辑使用 `str.strip("`")` 按字符集剥离，而非精确匹配前后缀。若 JSON 内容首尾存在反引号，会导致**正文数据被一同削除**，引发 JSON 解析错误或数据损坏。应改用正则精确剥离：
  ```python
  import re
  current_input = re.sub(r'^```(?:json)?\s*\n?', '', current_input, flags=re.IGNORECASE)
  current_input = re.sub(r'\n?```\s*$', '', current_input).strip()
  ```

- [x] **[REV-MP050607-BUG-002]** `schema_validator.py` 第 53 行：`healing_func(current_input, str(e))` 调用没有异常保护。若 `healing_func` 内部因网络超时等原因抛出异常，该异常会直接逃逸出 `validate_and_heal`，调用方收到的是一个意料之外的异常类型，破坏其 `except` 错误处理逻辑。应对 `healing_func` 调用加 `try/except` 保护，失败时统一转换为 `AutoHealingMaxRetriesExceeded` 上报：
  ```python
  try:
      current_input = healing_func(current_input, str(e))
  except Exception as heal_err:
      raise AutoHealingMaxRetriesExceeded(
          f"Healing function raised an exception after {attempts} attempts."
      ) from heal_err
  ```

- [x] **[REV-OB06-CON-001]** `cli_logger.py` 第 37 行：`json.JSONDecodeError` 解析失败时直接 `pass`。在并发写入导致行截断或格式损坏时，这种静默丢弃会导致日志内容无感知丢失。建议改为在 `stderr` 输出警告日志，让开发者知道部分日志已损坏被跳过。

- [x] **[REV-OB0405-CON-001]** `jsonl_storage.py` 第 25 行：`_rotate_if_needed()` 在 `try` 块外部调用。如果文件轮转过程（如 `os.replace`）因为磁盘空间不足或权限问题失败，该异常会直接透传给主业务逻辑，导致系统崩溃。应将轮转检查移入 `try` 块内，确保监控故障不反噬业务。

- [x] **[REV-OBEXPORTS-CON-001]** `exports.py`：T5 新增的 `jsonl_storage` 和 `cli_logger` 目前在 `bootstrap.py` 中尚未获得实例注入，全局 Exports 暴露的是默认值 `None`。必须在 `bootstrap.py` 中完善初始化逻辑，将具体引擎实例注入导出容器。

- [x] **[REV-SH01-FATAL-001] 架构级偏离：虚假的“形式安全”拦截**：`security.py` 及其在 `capability_hub.py` 中的集成，完全背离了《技能与工具层架构设计规格书》及 SH-P0-01 中对“安全原语”的定义。架构要求安全原语提供：1) 基于受限环境的底层 SDK（如 secure_fs 限制文件读取路径）；2) 不可绕开的系统层拦截与运行时沙盒阉割。而当前代码中的防线 `if request.metadata.get("unsafe") is True` 仅是个形式上的“防君子不防小人”标签，且 `allowed_domains` 白名单沦为摆设毫无实际过滤逻辑。这意味着目前系统对恶意大模型动作或第三方 MCP 越权**没有任何实质的物理隔离与访问控制，在防御设计上属于无效交付**，须推翻重构。

---

## P1 级建议与结论（重要功能/体验优化）

- [ ] **[REV-GW07-BUG-002]（二次审阅新增）** `responses.py` & `feishu_sender.py`：`ReplyText(content)` 的长度拦截目前硬编码在原语模型结构内部，不仅破坏了与具体通信平台解耦的设计，且超出限制时会粗暴地直接抛出异常，导致本该发给用户的超大段文本发生“静默烂尾”。**修复建议：** 移除 `responses.py` 中的字数校验兜底；将长度拦截移动到具体的 `feishu_sender.py` 内部发送前，并采用**切片分段发送**的思路（将超过 4000 字符的字符串切出多条连续的 payload 分别发往飞书），以彻底保障大文本输出的健壮性。

- [x] **[REV-GW07-CON-002]** `responses.py`：响应原语模块缺少统一的抽象基类或 `Protocol` 约束，未来新增 `ReplyCard`、`ReplyImage` 等原语类型时，发送器无法用统一类型提示接收"任意一种响应原语"，会造成方法签名上的类型扩散。建议新增 `ReplyPrimitive` 协议基类。

- [x] **[REV-GW0809-CON-001]** `feishu_sender.py`：当前仅支持 `ReplyText`（纯文本），但 T5 阶段的架构目标是"Agent 在浏览器抓取期间不断向飞书回传进度"，实际场景中进度消息通常使用飞书**消息卡片**。应规划 `send_card_reply` 接口的占位，保持扩展路径清晰。

- [ ] **[REV-OB06-BUG-001]** `cli_logger.py` 第 26 行：`tail()` 方法使用永久阻塞的 `while True` 循环，缺乏外部停止信号（Stop Event）或超时机制。这导致测试代码无法正常覆盖该方法（进程会挂死），且未来若作为后台异步任务运行时无法优雅关闭。

- [ ] **[REV-OB0405-BUG-001]** `jsonl_storage.py`：文件轮转逻辑存在 TOCTOU（检查时与使用时不一致）竞态风险。先 `stat()` 检查大小再 `replace()` 重命名，在多线程并发写入时可能导致多个线程同时触发轮转，造成 `FileNotFoundError` 或备份文件覆盖。在 T5 后的高并发场景需引入 `threading.Lock`。

---

## P2 级建议与结论（边缘优化/代码规范）

（暂无）
