#!/usr/bin/env python3
"""
T2 阶段：飞书长连接手动测试扩展辅助脚本

【写给 Python 初学者的导读】
这个脚本的作用是启动一个“飞书机器人”的本地接收服务。
当我们在这个脚本运行期间在飞书里给机器人发消息时，它能接收到消息，
并模拟大模型的思考过程，最终在控制台打印出处理结果。
为了能同时处理多个人发来的多条消息（即“并发”），这个脚本使用了比较高级的
“异步编程 (asyncio)” 和 “多进程 (multiprocessing)” 技术。
"""

import asyncio  # 引入异步 I/O 库，用于实现“同时做多件事”而不会互相卡住
import multiprocessing as mp  # 引入多进程库，用于创建完全独立的子进程来运行阻塞代码
import os  # 引入操作系统接口，用于读取环境变量、处理文件路径等
import sys  # 引入系统特定参数和函数，这里主要用来修改模块搜索路径
import time  # 引入时间库，用于计算程序运行耗时或让程序暂停

# 【设置项目根目录】
# __file__ 代表当前脚本文件的相对或绝对路径。我们通过 dirname 和 join 找到项目最外层目录（根目录）
# 然后将其加入到 sys.path 的最前面（索引为0）。这样 Python 才能正确识别并导入以 "src." 开头的我们自己写的模块。
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 导入项目中自己写的各种功能模块
from src.app.bootstrap import build_application  # 用于构建并初始化整个应用
from src.app.config import load_config  # 用于加载配置文件（如飞书的 AppID 等）
from src.app.config import AppConfig  # 配置的数据类型定义
from src.channel_gateway.domain.events import UniversalEvent, UniversalEventContent  # 统一的事件模型（代表一条规范化后的消息）
from src.model_provider.contracts import ModelMessage, ModelRequest  # 模型调用的数据结构定义
from src.storage_memory.contracts.models import HotMemoryItem  # 短期记忆的数据结构定义


def _extract_text_content(event: UniversalEvent) -> str:
    """
    这是一个辅助函数，作用是从复杂的飞书消息事件中，把用户发送的“纯文本”内容提取出来。
    """
    # 如果消息本身已经有简单的纯文本字段，并且不为空，直接返回它
    if isinstance(event.text, str) and event.text:
        return event.text
    
    # 如果消息是复杂的富文本（比如图文混排），我们需要遍历它的内容列表
    texts: list[str] = []
    for content in event.contents:
        # 挑选出类型为 "text" (文本) 的内容片段，保存起来
        if isinstance(content, UniversalEventContent) and content.type == "text":
            texts.append(str(content.data))
            
    # 如果找到了一个或多个文本片段，用空格把它们拼成一句完整的话返回
    if texts:
        return " ".join(texts)
        
    # 如果什么纯文本都没找到，就只能强行把所有内容转成字符串返回（作为保底机制）
    return str(event.contents)


async def run_extended_manual_test() -> None:
    """
    这是脚本的主函数（异步函数，注意前面的 async 关键字，表示它支持暂停和恢复）。
    它负责初始化核心组件、启动多进程，并开启事件循环来处理飞书消息。
    """
    print("=" * 60)
    print("准备启动 [T2 异步版] 飞书长连接进行手动测试...")
    print("=" * 60)

    # 1. 加载配置并构建应用核心模块
    config = load_config()
    app = build_application(config)

    # 检查是否配置了飞书参数（如果没有配置，连不上飞书服务器）
    if app.config.feishu is None:
        print("错误: 未找到飞书配置，请先运行 config-feishu 命令")
        return

    # 从初始化好的应用中提取我们需要用到的三个核心模块：
    observability = app.modules.observability_hub  # 监控与日志追踪模块
    model_provider = app.modules.model_provider    # 大模型调用模块
    storage_memory = app.modules.storage_memory    # 记忆存储模块

    # 获取环境变量控制的延迟时间（单位：秒）。默认是 0。
    # 作用：如果你设置了延迟（比如 5 秒），我们就能清楚地看到多条消息是不是在“同时”处理，而没有互相排队。
    artificial_delay = float(os.getenv("QF_MANUAL_TEST_DELAY_SECONDS", "0"))
    
    # 【核心架构经验：为什么需要多进程？】
    # 飞书官方的 SDK 内部非常霸道，它会强行接管 Python 的异步事件循环 (event loop)。
    # 如果我们直接在这里运行它，它会和我们自己写的 asyncio 循环冲突，报错 "This event loop is already running"。
    # 所以，我们使用 mp.get_context("spawn") 创建一个完全独立的“子进程”，把飞书 SDK 关在里面运行。
    process_context = mp.get_context("spawn")
    
    # 进程之间是隔离的，不能直接共享变量。所以我们创建一个“队列 (Queue)”作为通信管道。
    # 子进程收到飞书消息后，就塞进这个队列里；主进程则从队列里拿出来处理。
    event_queue = process_context.Queue() 
    
    # 配置并准备好这个独立的子进程
    long_connection_process = process_context.Process(
        target=_run_long_connection_process, # 子进程要运行的具体函数
        args=(app.config, event_queue),      # 传给函数的参数：配置对象和通信队列
        daemon=True,                         # 设置为守护进程（主进程退出时，子进程也会跟着被强行关闭）
    )
    
    # 创建一个集合用来保存正在运行的异步任务。
    # 这是一个 Python 异步编程的好习惯：防止后台任务还没跑完，就被 Python 的“垃圾回收 (GC)”机制意外清理掉。
    active_tasks: set[asyncio.Task[None]] = set()

    async def _handle_event(event: UniversalEvent) -> None:
        """
        这个函数负责处理单条收到的飞书消息。
        它完全在主进程的 asyncio 事件循环中执行，支持“同时处理多条消息（即异步并发）”。
        """
        # 生成一个唯一的追踪ID (trace_id)，就像快递单号，用来追踪这条消息的整个生命周期
        trace_id = observability.trace_id_generator()
        
        # 提取用户发送的文本内容
        text_content = _extract_text_content(event)
        
        # 判断这条消息是否需要“染色”（染色通常用于线上问题的特殊追踪和调试）
        is_colored = observability.is_request_colored({"trace_id": trace_id})
        
        # 构造一条记忆记录：记录用户此刻说了什么
        memory_item = HotMemoryItem(
            trace_id=trace_id,
            role="user",
            content=text_content,
        )
        
        # 确定是谁发的消息（群聊 ID 或 单聊用户 ID）
        session_id = event.room_id or event.user_id
        
        # 记录开始处理的时间，用于最后计算总共花了多少秒
        started_at = time.perf_counter()
        
        print(f"[开始处理] event_id={event.event_id} text={text_content}")
        
        # 【异步处理技巧：to_thread】
        # append_hot_memory 是一个“同步（会阻塞运行）”的函数。
        # 在异步程序中，如果一个函数运行太慢卡住了，会连累其他正在处理的消息也卡住。
        # 所以我们用 asyncio.to_thread 把它扔到一个后台线程去执行，这样就不会卡住主流程了。
        latest_memories = await asyncio.to_thread(
            storage_memory.append_hot_memory,
            "manual_test_agent", # 智能体的名称标识
            session_id,          # 会话ID
            memory_item,         # 要保存的记忆对象
            5,                   # 截断限制：最多保留最近的 5 条记忆
        )
        
        # 如果启动时设置了人工延迟，就在这里睡一会儿。
        # await asyncio.sleep 不会卡住整个程序，它只是暂停当前这条消息的处理，让出控制权给其他消息。
        if artificial_delay > 0:
            await asyncio.sleep(artificial_delay)
            
        # 构造发给大模型的请求：告诉大模型用户说了什么
        model_req = ModelRequest(
            messages=(ModelMessage(role="user", content=text_content),),
            model_tag="test-mock-model",
        )
        
        # 同样，调用大模型也是个慢动作，扔到后台线程去执行
        model_resp = await asyncio.to_thread(model_provider.invoke_sync, model_req)
        
        # 计算总耗时
        elapsed = time.perf_counter() - started_at
        
        # 打印最终的处理结果报告
        print("\n" + "=" * 40)
        print(f"[收到消息] User: {event.user_id}")
        print(f"[内容] {text_content}")
        print(f"[TraceID] {trace_id} (染色: {is_colored})")
        print(f"[记忆存储] 当前会话热记忆长度: {len(latest_memories)}")
        print(f"[模型返回] {model_resp.content} (Provider: {model_resp.provider_id})")
        print(f"[处理耗时] {elapsed:.2f}s")
        print("=" * 40 + "\n")

    async def _consume_event_loop() -> None:
        """
        这是一个死循环（守护任务）。
        它的工作就像一个不知疲倦的快递分拣员，一直盯着管道（队列），
        一旦发现子进程传来了新消息，就马上派发给处理函数。
        """
        while True:
            # 从队列里拿消息。如果队列是空的，这里会阻塞等待。
            # 为了不卡住整个异步循环，同样使用了 to_thread 把它放到后台线程去等。
            event = await asyncio.to_thread(event_queue.get)
            
            # 拿到消息后，创建一个“后台异步任务 (Task)”去处理它。
            # 这样“分拣员”就可以立刻回头去等下一条消息，实现了真正的“并发处理”。
            task = asyncio.create_task(_handle_event(event))
            active_tasks.add(task)
            # 当任务处理完时，调用回调函数自动从 active_tasks 集合中移除自己
            task.add_done_callback(active_tasks.discard)

    async def _run_long_connection() -> None:
        """
        这个函数负责管理飞书长连接子进程的生命周期。
        """
        # 正式启动子进程
        long_connection_process.start()
        try:
            # 只要子进程还在运行，主程序就在这里安静地等待（每隔 1 秒醒来看一眼）
            while long_connection_process.is_alive():
                await asyncio.sleep(1)
        finally:
            # 如果主程序要退出了（比如用户按了 Ctrl+C），确保子进程也被安全地终止掉
            if long_connection_process.is_alive():
                long_connection_process.terminate()
                long_connection_process.join(timeout=3)

    print("服务启动中...请在飞书向机器人发送消息。")
    if artificial_delay > 0:
        print(f"已启用异步验证延迟: {artificial_delay:.1f}s")
        print("可连续快速发送多条消息，观察是否并发完成。")
    print("=" * 60)
    
    # asyncio.gather 的作用是同时启动并等待这两个大任务：
    # 1. 不断从队列拿消息分发的分拣员任务 (_consume_event_loop)
    # 2. 维持飞书连接子进程的看守任务 (_run_long_connection)
    await asyncio.gather(_consume_event_loop(), _run_long_connection())


def _run_long_connection_process(config: AppConfig, event_queue: mp.Queue) -> None:
    """
    【这里是运行在独立子进程中的代码】
    在这个完全独立的世界（内存空间）里，我们需要重新构建一次应用环境。
    """
    app = build_application(config)
    gateway = app.modules.channel_gateway
    runtime = gateway.feishu_long_connection
    
    # 检查飞书长连接模块是否准备就绪
    if not runtime.initialized:
        raise RuntimeError(runtime.error or "feishu_long_connection_unavailable")

    def _on_text_event(event: UniversalEvent) -> None:
        """
        这是注册给飞书 SDK 的回调函数。
        每当飞书 SDK 收到一条新消息，就会自动调用这个函数。
        我们在里面做的唯一一件事，就是把收到的消息塞进管道（队列）里，传给主进程。
        """
        event_queue.put(event)

    # 启动飞书 SDK 的长连接。
    # 注意：这个方法内部是阻塞的，它会一直卡在这里收发网络请求，直到连接断开。
    # 这也是为什么我们必须把它放在一个独立的子进程里运行的原因。
    gateway.run_feishu_long_connection(
        app.config.feishu,
        _on_text_event,
    )


# 【脚本的入口点】
# 只有当在终端里直接运行这个脚本文件时（比如 python run_manual_test.py），这里的代码才会执行。
# 如果是被其他 Python 文件通过 import 导入的，这段代码不会执行。
if __name__ == "__main__":
    try:
        # 使用 asyncio.run 启动整个异步程序的主循环
        asyncio.run(run_extended_manual_test())
    except KeyboardInterrupt:
        # 捕捉用户在终端按下 Ctrl+C 产生的退出信号，优雅地结束程序
        print("\n手动测试结束。")