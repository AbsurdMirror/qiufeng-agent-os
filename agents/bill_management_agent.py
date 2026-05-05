from pathlib import Path
import sys
import sqlite3
import threading
import argparse
from contextvars import ContextVar
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Annotated

# 将项目根目录添加到 sys.path
sys.path.append(str(Path(__file__).parent.parent))

from pydantic import Field
from src.qfaos import QFAConfig, QFAEnum, QFAOS, qfaos_pytool, QFAEvent, QFAExecutionContext, QFASessionContext
from src.domain.errors import format_user_facing_error
from src.domain.models import ModelMessage
from src.domain.translators import (
    build_user_context_block,
    build_assistant_answer_block,
    build_tool_interaction_block,
)
from src.observability_hub.cli.tailer import CLILogTailer
from pytools.baidu_ocr_tool import BaiduOCRTool


def _tool_success(data: Any = None, message: str = "ok") -> Dict[str, Any]:
    return {"ok": True, "message": message, "data": data}


def _tool_error(error: Exception, code: str = "TOOL_ERROR") -> Dict[str, Any]:
    return {"ok": False, "code": code, "error": str(error)}


@dataclass
class BillCardItem:
    id: int
    category: str
    date: str
    amount: float
    remark: Optional[str]


class BillManager:
    def __init__(self, db_path: str = "bills.db"):
        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # 开启外键约束支持
                cursor.execute("PRAGMA foreign_keys = ON")
                # 创建分类表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS categories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE
                    )
                ''')
                # 创建账单表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS bills (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        category TEXT NOT NULL,
                        date TEXT NOT NULL,
                        amount REAL NOT NULL,
                        remark TEXT,
                        FOREIGN KEY (category) REFERENCES categories (name) ON UPDATE CASCADE
                    )
                ''')
                
                # 初始化默认分类
                default_categories = ["日常", "大件", "旅游", "未分类"]
                for cat in default_categories:
                    cursor.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat,))
                
                conn.commit()

    # --- 分类管理 ---
    def add_category(self, name: str) -> bool:
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("PRAGMA foreign_keys = ON")
                    cursor.execute("INSERT INTO categories (name) VALUES (?)", (name,))
                    conn.commit()
                    return True
        except sqlite3.IntegrityError:
            return False

    def delete_category(self, name: str) -> bool:
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA foreign_keys = ON")
                cursor.execute("DELETE FROM categories WHERE name = ?", (name,))
                conn.commit()
                return cursor.rowcount > 0

    def list_categories(self) -> List[str]:
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM categories")
                return [row[0] for row in cursor.fetchall()]

    def _category_exists(self, category: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM categories WHERE name = ? LIMIT 1", (category,))
            return cursor.fetchone() is not None

    @staticmethod
    def _validate_date(date: str) -> None:
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("date 格式必须为 YYYY-MM-DD") from exc

    # --- 账单管理 ---
    def add_bill(self, category: str, amount: float, date: str, remark: str = None) -> int:
        if not date:
            raise ValueError("date 参数不能为空，且必须为 YYYY-MM-DD")
        self._validate_date(date)
        if not self._category_exists(category):
            raise ValueError(f"分类不存在: {category}")
        
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("PRAGMA foreign_keys = ON")
                    cursor.execute(
                        "INSERT INTO bills (category, date, amount, remark) VALUES (?, ?, ?, ?)",
                        (category, date, amount, remark)
                    )
                    conn.commit()
                    return cursor.lastrowid
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"写入账单失败: {exc}") from exc
        except sqlite3.Error as exc:
            raise RuntimeError(f"数据库错误(add_bill): {exc}") from exc

    def update_bill(self, bill_id: int, category: str = None, amount: float = None, date: str = None, remark: str = None) -> bool:
        updates = []
        params = []
        if category:
            if not self._category_exists(category):
                raise ValueError(f"分类不存在: {category}")
            updates.append("category = ?")
            params.append(category)
        if amount is not None:
            updates.append("amount = ?")
            params.append(amount)
        if date:
            self._validate_date(date)
            updates.append("date = ?")
            params.append(date)
        if remark is not None:
            updates.append("remark = ?")
            params.append(remark)
        
        if not updates:
            return False
        
        params.append(bill_id)
        query = f"UPDATE bills SET {', '.join(updates)} WHERE id = ?"
        
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("PRAGMA foreign_keys = ON")
                    cursor.execute(query, tuple(params))
                    conn.commit()
                    return cursor.rowcount > 0
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"更新账单失败: {exc}") from exc
        except sqlite3.Error as exc:
            raise RuntimeError(f"数据库错误(update_bill): {exc}") from exc

    def delete_bill(self, bill_id: int) -> bool:
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM bills WHERE id = ?", (bill_id,))
                    conn.commit()
                    return cursor.rowcount > 0
        except sqlite3.Error as exc:
            raise RuntimeError(f"数据库错误(delete_bill): {exc}") from exc

    def get_bill_by_id(self, bill_id: int) -> Optional[Dict[str, Any]]:
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute("SELECT id, category, date, amount, remark FROM bills WHERE id = ?", (bill_id,))
                    row = cursor.fetchone()
                    return dict(row) if row else None
        except sqlite3.Error as exc:
            raise RuntimeError(f"数据库错误(get_bill_by_id): {exc}") from exc

    # --- 筛选与统计 ---
    def query_bills(self, start_date: str = None, end_date: str = None, category: str = None, 
                    min_amount: float = None, max_amount: float = None) -> List[Dict[str, Any]]:
        query = "SELECT id, category, date, amount, remark FROM bills WHERE 1=1"
        params = []
        
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        if category:
            query += " AND category = ?"
            params.append(category)
        if min_amount is not None:
            query += " AND amount >= ?"
            params.append(min_amount)
        if max_amount is not None:
            query += " AND amount <= ?"
            params.append(max_amount)
            
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute(query, tuple(params))
                    return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as exc:
            raise RuntimeError(f"数据库错误(query_bills): {exc}") from exc

    def get_statistics(self, start_date: str = None, end_date: str = None, category: str = None,
                       min_amount: float = None, max_amount: float = None) -> Dict[str, Any]:
        query = "SELECT category, SUM(amount) as total_amount, COUNT(*) as count FROM bills WHERE 1=1"
        params = []
        
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        if category:
            query += " AND category = ?"
            params.append(category)
        if min_amount is not None:
            query += " AND amount >= ?"
            params.append(min_amount)
        if max_amount is not None:
            query += " AND amount <= ?"
            params.append(max_amount)
            
        query += " GROUP BY category"
        
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute(query, tuple(params))
                    rows = cursor.fetchall()
                    
                    stats = {
                        "by_category": [dict(row) for row in rows],
                        "total_sum": sum(row["total_amount"] for row in rows),
                        "total_count": sum(row["count"] for row in rows)
                    }
                    return stats
        except sqlite3.Error as exc:
            raise RuntimeError(f"数据库错误(get_statistics): {exc}") from exc

# --- Agent 脚本主体 ---

# 1. 创建 QFAOS 实例
agent = QFAOS()
base_dir = Path(__file__).parent

# 2. 飞书渠道配置初始化
feishu_secret_path = base_dir / "feishu_secret"
feishu_secret = feishu_secret_path.read_text(encoding="utf-8").strip()

feishu_cfg = QFAConfig.Channel.Feishu(
    app_id="cli_a93a9efeb378dbd9",
    app_secret=feishu_secret,
    mode=QFAEnum.Feishu.Mode.long_connection,
)
agent.register_channel(QFAEnum.Channel.Feishu, feishu_cfg)

# 3. MiniMax 模型配置初始化
minimax_api_key_path = base_dir / "minimax_api_key"
minimax_api_key = minimax_api_key_path.read_text(encoding="utf-8").strip()

minimax_cfg = QFAConfig.Model.MiniMax(
    model_name="minimax/MiniMax-M2.7",
    api_key=minimax_api_key,
    base_url="https://api.minimaxi.com/v1",
)
agent.register_model(QFAEnum.Model.MiniMax, minimax_cfg)

# --- 全局上下文管理 ---
_current_session_ctx: ContextVar[Optional[Any]] = ContextVar("_current_session_ctx", default=None)

# 4. 账单管理工具实例化
bill_manager = BillManager(db_path=str(base_dir / "bills.db"))

# 5. 百度 OCR 工具实例化
baidu_api_key = (base_dir / "baidu_ocr_api_key").read_text(encoding="utf-8").strip()
baidu_secret_key = (base_dir / "baidu_ocr_secret_key").read_text(encoding="utf-8").strip()
ocr_tool = BaiduOCRTool(api_key=baidu_api_key, secret_key=baidu_secret_key)

async def _send_tool_card(tool_name: str, tool_desc: str, tool_msg: str) -> None:
    """发送工具调用的飞书卡片消息。"""
    session = _current_session_ctx.get()
    if session:
        await session.send_feishu_card_message(
            template_id="AAqeKTOLQ5WlC",
            template_variable={
                "tool_name": tool_name,
                "tool_desc": tool_desc,
                "tool_msg": tool_msg
            }
        )

# 5. 定义账单管理工具 (pytools)
# 注意：仅将账单操作工具暴露给 AI 模型，分类管理工具 (add_category, delete_category) 仅通过 CLI 使用。

@qfaos_pytool(id="list_categories")
async def list_categories() -> Annotated[Dict[str, Any], Field(description="包含分类列表的响应对象")]:
    """获取所有已定义的账单分类列表。"""
    try:
        categories = bill_manager.list_categories()
        await _send_tool_card("list_categories", "获取所有账单分类", ", ".join(categories))
        return _tool_success({"categories": categories})
    except Exception as e:
        return _tool_error(e, code="LIST_CATEGORIES_FAILED")


@qfaos_pytool(id="get_today_date")
async def get_today_date() -> Annotated[Dict[str, Any], Field(description="包含今日日期的响应对象")]:
    """返回今天的日期（YYYY-MM-DD）。"""
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        weekday = datetime.now().strftime("%A")
        
        await _send_tool_card("get_today_date", "获取当前标准日期", f"`{today}, 星期{weekday}`")
        return _tool_success({"today": f"{today}, 星期{weekday}"})
    except Exception as e:
        return _tool_error(e, code="GET_TODAY_DATE_FAILED")


@qfaos_pytool(id="add_bill")
async def add_bill(
    category: Annotated[str, Field(description="账单分类")],
    amount: Annotated[float, Field(description="账单金额")],
    date: Annotated[str, Field(description="账单日期，格式为 YYYY-MM-DD")],
    remark: Annotated[Optional[str], Field(description="备注信息")] = None
) -> Annotated[Dict[str, Any], Field(description="账单添加操作的结果")]:
    """添加一条新的账单记录。"""
    try:
        bill_id = bill_manager.add_bill(category, amount, date, remark)
        table_msg = (
            f"| 字段 | 内容 |\n"
            f"| :---: | :--- |\n"
            f"| 分类 | `{category}` |\n"
            f"| 金额 | `¥{amount:,.2f}` |\n"
            f"| 日期 | `{date}` |\n"
            f"| 备注 | `{remark or '无'}` |\n"
            f"| ID | `{bill_id}` |"
        )
        await _send_tool_card("add_bill", "录入单笔消费账单", table_msg)
        return _tool_success({"bill_id": bill_id}, message="账单添加成功")
    except Exception as e:
        return _tool_error(e, code="ADD_BILL_FAILED")

@qfaos_pytool(id="update_bill")
async def update_bill(
    bill_id: Annotated[int, Field(description="要修改的账单 ID")],
    category: Annotated[Optional[str], Field(description="新的分类")] = None,
    amount: Annotated[Optional[float], Field(description="新的金额")] = None,
    date: Annotated[Optional[str], Field(description="新的日期")] = None,
    remark: Annotated[Optional[str], Field(description="新的备注")] = None
) -> Annotated[Dict[str, Any], Field(description="账单修改操作的结果")]:
    """根据 ID 修改已有账单的信息。"""
    try:
        updated = bill_manager.update_bill(bill_id, category, amount, date, remark)
        if not updated:
            return {"ok": False, "code": "UPDATE_BILL_NOT_FOUND", "error": f"未找到可更新账单，bill_id={bill_id}"}
        
        updates_in_md = [f"- ID：`{bill_id}`"]
        if category: updates_in_md.append(f"- 分类 -> `{category}`")
        if amount is not None: updates_in_md.append(f"- 金额 -> `¥{amount:,.2f}`")
        if date: updates_in_md.append(f"- 日期 -> `{date}`")
        if remark is not None: updates_in_md.append(f"- 备注 -> `{remark or '无'}`")
        updates_in_md.append("- 结果：`成功`")
        
        await _send_tool_card(
            "update_bill",
            "修改现有账单记录",
            "\n".join(updates_in_md)
        )
            
        return _tool_success({"updated": True}, message="账单修改成功")
    except Exception as e:
        return _tool_error(e, code="UPDATE_BILL_FAILED")


@qfaos_pytool(id="delete_bill")
async def delete_bill(
    bill_id: Annotated[int, Field(description="要删除的账单 ID")]
) -> Annotated[Dict[str, Any], Field(description="账单删除操作的结果")]:
    """根据 ID 删除一条账单记录。"""
    try:
        bill = bill_manager.get_bill_by_id(bill_id)
        deleted = bill_manager.delete_bill(bill_id)
        if not deleted:
            return {"ok": False, "code": "DELETE_BILL_NOT_FOUND", "error": f"未找到可删除账单，bill_id={bill_id}"}
        
        table_msg = (
            f"| 字段 | 内容 |\n"
            f"| :--- | :--- |\n"
            f"| 状态 | `已删除` |\n"
            f"| ID | `{bill_id}` |\n"
            f"| 分类 | `{bill['category'] if bill else '未知'}` |\n"
            f"| 金额 | `¥{bill['amount'] if bill else 0:,.2f}` |\n"
            f"| 日期 | `{bill['date'] if bill else '未知'}` |\n"
            f"| 备注 | `{bill['remark'] if bill and bill['remark'] else '无'}` |"
        )
        await _send_tool_card("delete_bill", "删除指定账单记录", table_msg)
            
        return _tool_success({"deleted": True}, message="账单删除成功")
    except Exception as e:
        return _tool_error(e, code="DELETE_BILL_FAILED")


@qfaos_pytool(id="get_bill_by_id")
async def get_bill_by_id(
    bill_id: Annotated[int, Field(description="账单 ID")]
) -> Annotated[Dict[str, Any], Field(description="包含账单详情的响应对象")]:
    """根据 ID 获取单条账单的详细信息。"""
    try:
        bill = bill_manager.get_bill_by_id(bill_id)
        if bill is None:
            return {"ok": False, "code": "BILL_NOT_FOUND", "error": f"未找到账单，bill_id={bill_id}"}
        
        table_msg = (
            f"| 字段 | 内容 |\n"
            f"| :--- | :--- |\n"
            f"| ID | `{bill_id}` |\n"
            f"| 分类 | `{bill['category']}` |\n"
            f"| 金额 | `¥{bill['amount']:,.2f}` |\n"
            f"| 日期 | `{bill['date']}` |\n"
            f"| 备注 | `{bill['remark'] or '无'}` |"
        )
        await _send_tool_card("get_bill_by_id", "查询账单详细信息", table_msg)
            
        return _tool_success({"bill": bill})
    except Exception as e:
        return _tool_error(e, code="GET_BILL_FAILED")


@qfaos_pytool(id="query_bills")
async def query_bills(
    start_date: Annotated[Optional[str], Field(description="起始日期")] = None,
    end_date: Annotated[Optional[str], Field(description="结束日期")] = None,
    category: Annotated[Optional[str], Field(description="账单分类")] = None,
    min_amount: Annotated[Optional[float], Field(description="最小金额")] = None,
    max_amount: Annotated[Optional[float], Field(description="最大金额")] = None
) -> Annotated[Dict[str, Any], Field(description="包含筛选出的账单列表的响应对象")]:
    """根据日期范围、分类、金额范围等条件筛选账单。"""
    try:
        bills = bill_manager.query_bills(start_date, end_date, category, min_amount, max_amount)
        
        filter_info = [
            f"- 起始日期：`{start_date or '不限'}`",
            f"- 结束日期：`{end_date or '不限'}`",
            f"- 账单分类：`{category or '全部'}`",
            f"- 最小金额：`{f'¥{min_amount:,.2f}' if min_amount is not None else '不限'}`",
            f"- 最大金额：`{f'¥{max_amount:,.2f}' if max_amount is not None else '不限'}`",
            f"- 匹配结果：`{len(bills)}` 笔"
        ]
        await _send_tool_card("query_bills", "按条件筛选账单", "\n".join(filter_info))
            
        return _tool_success({"bills": bills})
    except Exception as e:
        return _tool_error(e, code="QUERY_BILLS_FAILED")


@qfaos_pytool(id="get_statistics")
async def get_statistics(
    start_date: Annotated[Optional[str], Field(description="起始日期")] = None,
    end_date: Annotated[Optional[str], Field(description="结束日期")] = None,
    category: Annotated[Optional[str], Field(description="账单分类")] = None,
    min_amount: Annotated[Optional[float], Field(description="最小金额")] = None,
    max_amount: Annotated[Optional[float], Field(description="最大金额")] = None
) -> Annotated[Dict[str, Any], Field(description="包含统计分析数据的响应对象")]:
    """统计指定范围内的账单数据（总和、条数及按分类统计）。"""
    try:
        stats = bill_manager.get_statistics(start_date, end_date, category, min_amount, max_amount)
        
        stat_info = [
            f"- 起始日期：`{start_date or '不限'}`",
            f"- 结束日期：`{end_date or '不限'}`",
            f"- 账单分类：`{category or '全部'}`",
            f"- 最小金额：`{f'¥{min_amount:,.2f}' if min_amount is not None else '不限'}`",
            f"- 最大金额：`{f'¥{max_amount:,.2f}' if max_amount is not None else '不限'}`",
            f"- 合计金额：`¥{stats['total_sum']:,.2f}`",
            f"- 合计笔数：`{stats['total_count']}` 笔"
        ]
        await _send_tool_card("get_statistics", "统计账单支出数据", "\n".join(stat_info))
            
        return _tool_success({"statistics": stats})
    except Exception as e:
        return _tool_error(e, code="GET_STATISTICS_FAILED")


@qfaos_pytool(id="send_bill_card")
async def send_bill_card(
    bills: Annotated[List[BillCardItem], Field(description="账单明细列表，每项为 BillCardItem（包含 id, category, date, amount, remark）")]
) -> Annotated[Dict[str, Any], Field(description="卡片发送操作的结果")]:
    """将账单明细以美观的飞书卡片形式发送给用户。"""
    try:
        session = _current_session_ctx.get()
        if not session:
            return _tool_error(RuntimeError("Session context not found"))

        if not bills:
            await session.send_message(QFAEnum.Channel.Feishu, "没有找到符合条件的账单。")
            return _tool_success(message="No bills to send")

        total_sum = sum(b.amount for b in bills)
        formatted_bills = []
        for b in bills:
            formatted_bills.append({
                "date": b.date,
                "amount": f"{b.amount:.2f}",
                "remark": b.remark or "无",
                "category": b.category,
                "id": b.id
            })

        # 构造卡片变量
        template_variable = {
            "total": f"¥{total_sum:,.2f}",
            "object_list_1": formatted_bills
        }

        # 写死 Template ID
        template_id = "AAqezhmtrTuZ0" 

        await session.send_feishu_card_message(
            template_id=template_id,
            template_variable=template_variable
        )
        
        return _tool_success(message="账单卡片发送成功")
    except Exception as e:
        return _tool_error(e, code="SEND_BILL_CARD_FAILED")


# 6. 注册工具到 Agent
agent.register_pytool(list_categories)
agent.register_pytool(get_today_date)
agent.register_pytool(add_bill)
agent.register_pytool(update_bill)
agent.register_pytool(delete_bill)
agent.register_pytool(get_bill_by_id)
agent.register_pytool(query_bills)
agent.register_pytool(get_statistics)
agent.register_pytool(send_bill_card)

# 7. 注册记忆策略与观测 log 策略
memory_cfg = QFAConfig.Memory(
    backend=QFAEnum.Memory.Backend.jsonl,
)
agent.register_memory(memory_cfg)

log_cfg = QFAConfig.Observability.Log(
    jsonl_log_dir="./bill_agent_logs",
)
agent.register_observability_log(log_cfg)

has_inject_system_prompt_sessions: set[str] = set()
system_prompt_date_by_session: dict[str, str] = {} #注入的日期

# 8. 注册 Agent 编排流程 (custom_execute)
@agent.custom_execute
async def execute(event:QFAEvent, ctx:QFAExecutionContext) -> None:

    system_prompt = f"""
    你是一个极简、高效的账单管理助手。你具备以下自动化处理能力：
    1. **主动询问**：如果用户提供的账单信息不完整（如缺少金额），请主动询问用户。
    2. **智能推测**：根据用户的描述自动推测最合适的账单分类（例如“吃火锅”推测为“餐饮”）。
    3. **自动备注**：根据上下文自动为账单补充有意义的备注信息。
    4. **可视化展示**：当用户要求查看账单明细、查询账单或获取统计后的明细时，**必须调用 `send_bill_card` 工具**，将账单列表以卡片形式展示给用户，而不是直接输出文本列表。
    
    **重要指令**
    - 账单的分类是固定的，你在添加或修改账单的分类时，必须保证分类在已存在的分类列表中。
    - 回答用户账单信息时必须是真的调用工具查询到的账单信息，不能你自己编造。尤其是新建账单后一定要再次读取验证。
    - 当你查询到账单数据后，请立即调用 `send_bill_card` 工具进行展示。发送账单后，不需要再输出文本账单，只需要回复'已发送账单'。

    请直接根据用户的意图调用工具或直接回答用户问题。

    今天的日期是: {datetime.now().strftime("%Y-%m-%d")}, 星期{datetime.now().strftime("%A")}
    """
    session_ctx = ctx.get_session_ctx(event.session_id)
    if event.session_id not in has_inject_system_prompt_sessions:
        # 使用 set_system_prompt 以确保系统提示词不被裁剪
        await session_ctx.set_system_prompt(system_prompt)
        system_prompt_date_by_session[event.session_id] = datetime.now().strftime("%Y-%m-%d")
        has_inject_system_prompt_sessions.add(event.session_id)
    else:
        # 日期有变化，需要更新系统提示词 (source="base_prompt" 会覆盖旧的)
        today = datetime.now().strftime("%Y-%m-%d")
        if system_prompt_date_by_session[event.session_id] != today:
            # 也可以使用不同的 source 或直接覆盖 base_prompt
            # 这里选择覆盖 base_prompt 以保持简洁
            await session_ctx.set_system_prompt(system_prompt)
            system_prompt_date_by_session[event.session_id] = today

    token = _current_session_ctx.set(session_ctx)
    try:
        await _do_execute(event, session_ctx)
    finally:
        _current_session_ctx.reset(token)

async def _do_execute(event:QFAEvent, session_ctx: QFASessionContext) -> None:
    session_ctx.record(
        "bill.event.received",
        {"channel": str(event.channel), "type": str(event.type), "session_id": event.session_id},
        level="INFO",
    )

    if event.channel != QFAEnum.Channel.Feishu:
        session_ctx.record("bill.event.ignored", {"reason": "unsupported_channel"}, level="DEBUG")
        return

    # --- 处理图片消息 (ImageMessage) ---
    if event.type == QFAEnum.Event.ImageMessage:
        image_key = event.payload
        session_ctx.record("bill.event.image", {"image_key": image_key}, level="INFO")
        
        await session_ctx.send_message(QFAEnum.Channel.Feishu, "收到图片，正在识别中...")
        
        try:
            # 1. 下载图片
            local_path = await session_ctx.download_image(image_key)
            
            # 2. 调用 OCR 识别文字
            ocr_res = ocr_tool.recognize_text(image_path=local_path)
            
            if not ocr_res.get("success"):
                await session_ctx.send_message(QFAEnum.Channel.Feishu, f"图片识别失败: {ocr_res.get('error_msg')}")
                return
            
            words = [w.get("words", "") for w in ocr_res.get("words_result", [])]
            ocr_text = "\n".join(words)
            
            session_ctx.record("bill.ocr.success", {"text_len": len(ocr_text)}, level="INFO")
            
            # 3. 将 OCR 结果拼接成用户提示词
            user_input = f"我上传了一张图片，根据图片内容处理一下。以下是 OCR 识别出的文字内容：\n\n{ocr_text}"
            
        except Exception as e:
            session_ctx.record("bill.ocr.error", {"error": str(e)}, level="ERROR")
            await session_ctx.send_message(QFAEnum.Channel.Feishu, f"处理图片时发生错误: {str(e)}")
            return

    # --- 处理文本消息 (TextMessage) ---
    elif event.type == QFAEnum.Event.TextMessage:
        user_input = event.payload.strip()
    else:
        session_ctx.record("bill.event.ignored", {"reason": "not_text_or_image_message"}, level="DEBUG")
        return
    
    # --- 命令行模式 (/开头) ---
    if user_input.startswith("/"):
        session_ctx.record("bill.mode.cli", {"input": user_input}, level="INFO")
        parts = user_input[1:].split()
        cmd = parts[0] if parts else ""
        args = parts[1:]

        if cmd == "help":
            help_text = "账单管理命令帮助：\n" \
                      + "/add_category [名称] - 添加分类\n" \
                      + "/delete_category [名称] - 删除分类\n" \
                      + "/list_categories - 列出所有分类\n" \
                      + "/add_bill [分类] [金额] [日期] [备注] - 添加账单 (日期必填，备注可选)\n" \
                      + "/update_bill [ID] [分类] [金额] [日期] [备注] - 修改账单 (除ID外均可选，不修改传 -)\n" \
                      + "/delete_bill [ID] - 删除账单\n" \
                      + "/get_bill [ID] - 获取账单详情\n" \
                      + "/query_bills - 查询所有账单\n" \
                      + "/get_statistics - 获取账单统计\n" \
                      + "/clear - 清除当前会话的上下文记忆\n" \
                      + "/help - 显示此帮助信息\n"
            await session_ctx.send_message(QFAEnum.Channel.Feishu, help_text)
            return

        # 完整的命令行映射逻辑
        try:
            if cmd == "clear":
                await session_ctx.clear_history()
                # 同时清除本地的系统提示词注入标记
                if event.session_id in has_inject_system_prompt_sessions:
                    has_inject_system_prompt_sessions.remove(event.session_id)
                if event.session_id in system_prompt_date_by_session:
                    del system_prompt_date_by_session[event.session_id]
                await session_ctx.send_message(QFAEnum.Channel.Feishu, "上下文记忆已清除。")
            elif cmd == "add_category" and len(args) >= 1:
                res = bill_manager.add_category(args[0])
                await session_ctx.send_message(QFAEnum.Channel.Feishu, f"分类添加{'成功' if res else '失败'}")
            elif cmd == "delete_category" and len(args) >= 1:
                res = bill_manager.delete_category(args[0])
                await session_ctx.send_message(QFAEnum.Channel.Feishu, f"分类删除{'成功' if res else '失败'}")
            elif cmd == "list_categories":
                res = bill_manager.list_categories()
                await session_ctx.send_message(QFAEnum.Channel.Feishu, f"当前分类: {', '.join(res)}")
            elif cmd == "add_bill" and len(args) >= 3:
                category = args[0]
                amount = float(args[1])
                date = args[2]
                remark = args[3] if len(args) > 3 and args[3] != "-" else None
                res_id = bill_manager.add_bill(category, amount, date, remark)
                await session_ctx.send_message(QFAEnum.Channel.Feishu, f"账单添加成功，ID: {res_id}")
            elif cmd == "update_bill" and len(args) >= 1:
                bill_id = int(args[0])
                category = args[1] if len(args) > 1 and args[1] != "-" else None
                amount = float(args[2]) if len(args) > 2 and args[2] != "-" else None
                date = args[3] if len(args) > 3 and args[3] != "-" else None
                remark = args[4] if len(args) > 4 and args[4] != "-" else None
                res = bill_manager.update_bill(bill_id, category, amount, date, remark)
                await session_ctx.send_message(QFAEnum.Channel.Feishu, f"账单修改{'成功' if res else '失败'}")
            elif cmd == "delete_bill" and len(args) >= 1:
                res = bill_manager.delete_bill(int(args[0]))
                await session_ctx.send_message(QFAEnum.Channel.Feishu, f"账单删除{'成功' if res else '失败'}")
            elif cmd == "get_bill" and len(args) >= 1:
                res = bill_manager.get_bill_by_id(int(args[0]))
                if res:
                    await session_ctx.send_message(QFAEnum.Channel.Feishu, f"账单详情: {res}")
                else:
                    await session_ctx.send_message(QFAEnum.Channel.Feishu, "未找到该账单")
            elif cmd == "query_bills":
                res = bill_manager.query_bills()
                resp = "\n".join([f"ID:{b['id']} | {b['date']} | {b['category']} | {b['amount']} | {b['remark'] or ''}" for b in res])
                await session_ctx.send_message(QFAEnum.Channel.Feishu, resp or "暂无账单记录")
            elif cmd == "get_statistics":
                res = bill_manager.get_statistics()
                resp = f"总额: {res['total_sum']}, 总笔数: {res['total_count']}\n分类统计: "
                resp += ", ".join([f"{c['category']}: {c['total_amount']}" for c in res['by_category']])
                await session_ctx.send_message(QFAEnum.Channel.Feishu, resp)
            else:
                await session_ctx.send_message(QFAEnum.Channel.Feishu, f"未知命令或参数不足: {cmd}，输入 /help 查看支持的命令。")
        except Exception as e:
            session_ctx.record("bill.cli.error", {"error": str(e)}, level="ERROR")
            await session_ctx.send_message(QFAEnum.Channel.Feishu, f"命令执行出错: {str(e)}")
        return

    # --- AI 模型模式 ---
    session_ctx.record("bill.mode.ai", {"input": user_input}, level="INFO")
    MAX_ROUND = 30

    # 1. 记录用户输入块
    await session_ctx.append_context_block(
        build_user_context_block(
            block_id=f"user-{datetime.now().timestamp()}",
            user_message=ModelMessage(role="user", content=user_input),
            token_count=0
        )
    )

    prompt = "" # 后续轮次不再重复发送初始 prompt，已在 memory 中
    for i in range(MAX_ROUND):
        session_ctx.record("bill.ai.round.begin", {"round": i}, level="DEBUG")
        model_output = await session_ctx.model_ask(
            minimax_cfg,
            prompt,
            tools_mode="all",
        )
        
        if not model_output.model_response.success:
            session_ctx.record("bill.ai.model.error", {"error": model_output.model_response.repair_reason}, level="ERROR")
            await session_ctx.send_message(QFAEnum.Channel.Feishu, f"模型调用失败: {model_output.model_response.repair_reason}")
            return

        session_ctx.record("bill.ai.model.raw", {"raw": str(model_output)}, level="INFO")
        
        if model_output.is_pytool_call:
            tool_messages = []
            for tool_call in model_output.tool_calls:
                session_ctx.record(
                    "bill.ai.tool.call",
                    {
                        "tool_name": tool_call.capability_id,
                        "payload": dict(tool_call.payload),
                        "metadata": dict(tool_call.metadata),
                    },
                    level="INFO",
                )
                try:
                    response = await session_ctx.call_pytool(tool_call)
                    tool_messages.append(response.tool_message)
                    session_ctx.record(
                        "bill.ai.tool.result",
                        {
                            "tool_name": response.tool_name,
                            "tool_call_id": response.tool_call_id,
                            "output": response.output,
                        },
                        level="INFO",
                    )
                except Exception as e:
                    error_text = format_user_facing_error(e, summary=f"执行工具 {tool_call.capability_id} 失败")
                    session_ctx.record("bill.ai.tool.result.error", {"error": error_text}, level="ERROR")
                    await session_ctx.send_message(QFAEnum.Channel.Feishu, error_text)
                    return
            
            # 记录工具交互块 (Assistant Call + Tool Results)
            if model_output.assistant_message:
                await session_ctx.append_context_block(
                    build_tool_interaction_block(
                        block_id=f"tool-blk-{datetime.now().timestamp()}",
                        assistant_message=model_output.assistant_message,
                        tool_messages=tuple(tool_messages),
                        token_count=0
                    )
                )
            
            prompt = ""
        
        elif model_output.is_answer:
            if model_output.assistant_message:
                # 记录助手回答块
                await session_ctx.append_context_block(
                    build_assistant_answer_block(
                        block_id=f"ans-blk-{datetime.now().timestamp()}",
                        assistant_message=model_output.assistant_message,
                        token_count=0
                    )
                )

            response_text = model_output.response_text or ""
            # 去一下开头的换行
            response_text = response_text.lstrip("\n")
            
            if not response_text:
                session_ctx.record("bill.ai.answer.empty", {"model": minimax_cfg.model_name}, level="WARNING")
                response_text = "抱歉，我未能生成有效的回复，请稍后再试。"
            
            session_ctx.record("bill.ai.answer", {"text": response_text}, level="INFO")
            await session_ctx.send_message(QFAEnum.Channel.Feishu, response_text)
            break
    else:
        session_ctx.record("bill.ai.exhausted", {"max_round": MAX_ROUND}, level="WARNING")
        await session_ctx.send_message(QFAEnum.Channel.Feishu, f"抱歉，我尝试了 {MAX_ROUND} 次仍未完成您的请求。")

# 9. 运行 Agent
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="账单管理智能体")
    parser.add_argument("--console-log", action="store_true", help="是否在控制台打印实时日志")
    args = parser.parse_args()

    if args.console_log:
        # 启动日志追踪线程
        log_file = Path("./bill_agent_logs/debug_trace.jsonl")
        tailer = CLILogTailer(log_file=str(log_file))
        
        stop_event = threading.Event()
        log_thread = threading.Thread(
            target=tailer.tail, 
            kwargs={"stop_event": stop_event}, 
            daemon=True
        )
        log_thread.start()
        print(f"--- 已启动实时日志打印 (日志文件: {log_file}) ---")

    try:
        agent.run()
    except KeyboardInterrupt:
        print("\nAgent 已停止运行。")
        sys.exit(0)
