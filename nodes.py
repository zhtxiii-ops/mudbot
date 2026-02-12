"""
LangGraph 图节点模块
定义智能体状态图中的所有节点函数和辅助工具。
"""
import os
import time
import json
import re
from concurrent.futures import ThreadPoolExecutor, Future

import config
from config import Colors
from state import AgentState


# ============================================================
#  全局后台线程池（用于并行知识管理）
# ============================================================
_kb_executor = ThreadPoolExecutor(max_workers=1)


# ============================================================
#  辅助函数
# ============================================================

def log_colored(tag: str, message: str, color: str = None):
    """带颜色的日志输出，同时写入文件"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    if color:
        formatted_msg = f"[{timestamp}] {color}[{tag}] {message}{Colors.RESET}"
    else:
        formatted_msg = f"[{timestamp}] [{tag}] {message}"

    print(formatted_msg)

    with open(config.LOG_FILE, "a", encoding="utf-8") as f:
        f.write(formatted_msg + "\n")


def load_kb(phase: int = None) -> list[dict]:
    """
    从文件加载知识库。
    如果指定 phase，加载对应阶段的知识库；否则加载默认知识库。
    """
    if phase is not None:
        kb_file = os.path.join(config.KB_DIR, f"knowledge_base_phase_{phase}.json")
    else:
        kb_file = config.KB_FILE

    if not os.path.exists(kb_file):
        return []
    try:
        with open(kb_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            # 兼容旧格式（list[str] → list[dict]）
            result = []
            for item in data:
                if isinstance(item, str):
                    result.append({"content": item, "category": "unknown"})
                elif isinstance(item, dict):
                    result.append(item)
            return result
    except json.JSONDecodeError:
        return []


def save_kb(kb: list[dict], phase: int = None):
    """
    持久化知识库到文件。
    如果指定 phase，保存到对应阶段的知识库文件。
    """
    if phase is not None:
        os.makedirs(config.KB_DIR, exist_ok=True)
        kb_file = os.path.join(config.KB_DIR, f"knowledge_base_phase_{phase}.json")
    else:
        kb_file = config.KB_FILE

    with open(kb_file, "w", encoding="utf-8") as f:
        json.dump(kb, f, ensure_ascii=False, indent=2)


def load_all_previous_kb(current_phase: int) -> list[dict]:
    """加载当前阶段之前所有阶段的知识库"""
    all_kb = []
    for p in range(1, current_phase):
        kb = load_kb(phase=p)
        for entry in kb:
            entry_with_phase = dict(entry)
            entry_with_phase["from_phase"] = p
            all_kb.append(entry_with_phase)
    return all_kb


def get_aggregated_kb(current_phase: int, current_kb: list[dict]) -> list[dict]:
    """
    获取汇总后的知识库（历史阶段 + 当前阶段）。
    用于给 LLM 提供完整上下文。
    """
    all_kb = load_all_previous_kb(current_phase)
    # 合并当前阶段知识（注意避免重复引用，虽然这里是新建列表）
    all_kb.extend(current_kb)
    return all_kb


# ============================================================
#  图节点
# ============================================================

def observe(state: AgentState) -> dict:
    """
    观察节点：从 Socket 接收服务器输出。
    
    如果连接断开（receive 返回 None），设置 should_reconnect=True。
    """
    client = state["client"]

    server_output = client.receive()

    if server_output is None:
        return {
            "server_output": "",
            "server_output_clean": "",
            "should_reconnect": True,
        }

    log_colored("服务器", server_output)

    server_output_clean = client.clean_ansi(server_output)
    # Filter out specific compiler warnings
    # Example: 编译时段错误：/cmds/usr/inventory.c line 32: Warning: Unu...
    server_output_clean = re.sub(r'(?m)^.*?编译时段错误.*line \d+: Warning: Unu.*$', '', server_output_clean)

    # Filter out garbage characters (like ^X^_'VF*Z) which are likely Telnet negotiation artifacts
    # Matches lines containing VF*Z or similar short garbage
    server_output_clean = re.sub(r'(?m)^.*VF\*Z.*$', '', server_output_clean)
    
    server_output_clean = server_output_clean.strip()

    return {
        "server_output": server_output,
        "server_output_clean": server_output_clean,
        "should_reconnect": False,
    }


def analyze(state: AgentState) -> dict:
    """
    分析节点：接收规划者分配的任务，执行分析并决定下一步行动。
    
    职责：
    1. 根据当前任务和服务器输出决定 payload
    2. 判断当前任务是否已完成，如完成则设置 task_completed=True
    3. 识别环境类型（阶段1任务）
    """
    llm = state["llm"]
    server_output_clean = state["server_output_clean"]
    current_task = state.get("current_task", {})
    tasks = list(state.get("tasks", []))
    knowledge_base = state.get("knowledge_base", [])
    history = state.get("history", [])
    phase = state.get("phase", 1)
    phase_name = state.get("phase_name", "未知")
    environment_type = state.get("environment_type", "unknown")

    # 构建知识库字符串（使用聚合后的全量知识）
    full_kb = get_aggregated_kb(phase, knowledge_base)
    kb_str = ""
    if full_kb:
        for entry in full_kb[-30:]:  # 增加展示数量
            if isinstance(entry, dict):
                kb_str += f"- [阶段{entry.get('from_phase', phase)}][{entry.get('category', '?')}] {entry.get('content', '')}\n"
            else:
                kb_str += f"- {entry}\n"
    else:
        kb_str = "暂无。"

    # 构建最近历史
    recent_history = history[-config.MAX_HISTORY_ROUNDS:]
    history_str = "\n".join(recent_history)

    # 当前任务信息
    task_desc = current_task.get("description", "无特定任务")
    task_plan = current_task.get("plan", "无特定计划")
    task_id = current_task.get("id", "?")

    system_prompt = f"""\
你是一个自主智能体，正在通过 Socket 连接与远程服务器交互。

当前阶段: {phase} - {phase_name}
当前任务 [{task_id}]: {task_desc}
执行计划: {task_plan}

当前知识库:
{kb_str}

交互历史 (Client -> Server):
{history_str}

服务器的最后输出是："{server_output_clean}"

你的任务：
1. 分析服务器的响应，判断它与当前任务的关系。注意有些输出并非输入的直接响应，可能是服务器的自然输出或者是之前输入的延迟响应，需要仔细辨别。
2. 根据执行计划，决定下一步应该发送什么命令。当陷入困境时，查看帮助系统。
3. 判断当前任务是否已经完成（有足够信息得出结论）。
4. 如果任务涉及环境识别，给出环境类型。

严格以 JSON 格式输出：
{{
    "analysis": "你的详细分析...",
    "next_payload": "下一步要发送的具体字符串",
    "task_completed": true/false,
    "task_result": "如果任务完成，简要总结结果；否则为空",
    "environment_type": "如果识别了环境类型填写(mud/shell/chat/llm_qa/bbs/other/non_text)，否则填 null"
}}
"""

    user_msg = f"服务器说：{server_output_clean}。根据任务 [{task_id}]，你的下一步行动是什么？"

    print("[*] 思考中...")

    def main_logic_validator(res):
        return isinstance(res, dict) and "analysis" in res

    decision = llm.call_with_retry(
        system_prompt, user_msg,
        json_mode=True,
        validator=main_logic_validator,
    )

    # 解析决策
    analysis = decision.get("analysis", "无分析")
    payload = decision.get("next_payload", "")
    task_done = decision.get("task_completed", False)
    task_result = decision.get("task_result", "")
    env_type = decision.get("environment_type")

    log_colored("分析", f"[{task_id}] {analysis}", Colors.CYAN)

    result = {
        "analysis": analysis,
        "payload": payload,
        "task_completed": False,  # 默认不完成
    }

    # 处理环境类型识别
    if env_type and env_type != "null" and env_type is not None:
        result["environment_type"] = env_type
        log_colored("分析", f"识别环境类型: {env_type}", Colors.CYAN)

    # 处理任务完成
    if task_done:
        log_colored("分析", f"任务 [{task_id}] 已完成: {task_result}", Colors.GREEN)
        # 更新任务列表中的状态
        for t in tasks:
            if t["id"] == current_task.get("id"):
                t["status"] = "completed"
                t["result"] = task_result
                break
        current_task_updated = dict(current_task)
        current_task_updated["status"] = "completed"
        current_task_updated["result"] = task_result
        result["task_completed"] = True
        result["tasks"] = tasks
        result["current_task"] = current_task_updated
    else:
        log_colored("分析", f"任务 [{task_id}] 继续执行中...", Colors.YELLOW)

    return result


def manage_knowledge(state: AgentState) -> dict:
    """
    知识管理节点：act 之后执行。
    
    功能：
    1. 按阶段管理独立的知识库
    2. 区分信息类别：input_triggered（输入导致的输出）vs spontaneous（自发输出）
    3. 定期整理知识库（合并重复、更新过时、按类别归类）
    4. 根据当前阶段任务分析知识库建设重点
    """
    llm = state["llm"]
    history = state.get("history", [])
    knowledge_base = list(state.get("knowledge_base", []))  # 拷贝
    phase = state.get("phase", 1)
    phase_name = state.get("phase_name", "未知")
    tasks = state.get("tasks", [])
    counter = state.get("kb_consolidation_counter", 0)
    server_output_clean = state.get("server_output_clean", "")

    if not history and not tasks:
        # 即使没有历史，如果只是为了整理或保存，也应该允许执行（但act后通常有历史）
        # 这里保留原逻辑，如果没有history则不处理新知识，但仍需返回
        return {"knowledge_base": knowledge_base, "kb_consolidation_counter": counter}

    # 构建当前阶段任务摘要
    tasks_str = ""
    for t in tasks:
        tasks_str += f"- [{t.get('id', '?')}] {t.get('description', '')[:80]} (状态: {t.get('status', '?')})\n"

    # 加载以前阶段的知识库作为参考（全量上下文）
    full_kb = get_aggregated_kb(phase, knowledge_base)
    # 以前阶段（仅用于prompt展示区分）
    prev_kb = load_all_previous_kb(phase)
    prev_kb_str = ""
    if prev_kb:
        for entry in prev_kb[-15:]:
            prev_kb_str += f"- [阶段{entry.get('from_phase', '?')}][{entry.get('category', '?')}] {entry.get('content', '')}\n"
    else:
        prev_kb_str = "无以前阶段的知识。"

    # 构建当前知识库字符串
    kb_str = ""
    if knowledge_base:
        for entry in knowledge_base:
            if isinstance(entry, dict):
                kb_str += f"- [{entry.get('category', '?')}] {entry.get('content', '')}\n"
            else:
                kb_str += f"- {entry}\n"
    else:
        kb_str = "暂无。"

    # 构建交互历史字符串
    recent_history = history[-config.MAX_HISTORY_ROUNDS:]
    history_str = "\n".join([f"{i+1}. {h}" for i, h in enumerate(recent_history)])

    system_prompt = f"""\
你是一个知识库管理员。你的职责是为当前阶段管理专门的知识库。

当前阶段: {phase} - {phase_name}

当前阶段的任务:
{tasks_str}

以前阶段的知识库（参考）:
{prev_kb_str}

当前阶段知识库:
{kb_str}

最近的交互历史:
{history_str}

服务器最新输出:
"{server_output_clean}"

你的任务：
1. 根据当前阶段的任务，分析知识库建设的重点方向。
2. 从交互历史中提取有价值的新信息，更新到知识库中,额外列出新信息中出现的与当前阶段任务相关的关键词。
3. 每条知识必须标注类别 category：
   - "input_triggered": 这条信息是我们发送命令后，服务器响应中包含的信息
   - "spontaneous": 这条信息是没有我们输入也会产生的输出（如欢迎信息、系统广播、定时消息）
4. 已存在于知识库中的重复信息不要再次添加。
5. 无意义的系统噪音不要记录。

严格以 JSON 格式输出：
{{
    "kb_focus": "当前阶段知识库建设的重点方向",
    "reasoning": "你的分析思路...",
    "new_entries": [
        {{"content": "知识内容...", "category": "input_triggered 或 spontaneous"}}
    ],
    "keywords": ["关键词1", "关键词2", ...]
}}

如果没有需要添加的新知识，new_entries 应为空列表 []。
"""

    user_msg = "请审查交互历史并更新当前阶段的知识库。"

    log_colored("知识管理", f"正在审查交互历史（阶段 {phase}）...", Colors.MAGENTA)

    def kb_validator(res):
        return isinstance(res, dict) and "new_entries" in res and isinstance(res.get("new_entries"), list)

    result = llm.call_with_retry(
        system_prompt, user_msg,
        json_mode=True,
        validator=kb_validator,
    )

    kb_focus = result.get("kb_focus", "")
    new_entries = result.get("new_entries", [])
    reasoning = result.get("reasoning", "")

    if kb_focus:
        # log_colored("知识管理", f"知识建设重点: {kb_focus}", Colors.MAGENTA)
        pass
    if reasoning:
        # log_colored("知识管理", f"审查结论: {reasoning}", Colors.MAGENTA)
        pass

    added_count = 0
    for entry in new_entries:
        if not entry or not isinstance(entry, dict):
            continue
        content = entry.get("content", "")
        category = entry.get("category", "unknown")
        if not content:
            continue
        # 检查重复
        is_dup = any(
            e.get("content") == content
            for e in knowledge_base
            if isinstance(e, dict)
        )
        if is_dup:
            # log_colored("知识管理", f"跳过重复: {content}", Colors.RESET)
            continue
        knowledge_base.append({"content": content, "category": category})
        log_colored("知识管理", f"新增知识 [{category}]: {content}", Colors.MAGENTA)
        added_count += 1

    counter += 1

    if added_count > 0:
        save_kb(knowledge_base, phase=phase)
        log_colored("知识管理", f"共新增 {added_count} 条知识，已持久化。", Colors.MAGENTA)
    else:
        # log_colored("知识管理", "无需更新知识库。", Colors.RESET)
        pass

    # ------------------------------------------------------------------
    # 定期整理知识库
    # ------------------------------------------------------------------
    if counter >= config.KB_CONSOLIDATION_INTERVAL:
        log_colored("知识管理", "开始定期整理知识库...", Colors.MAGENTA)
        knowledge_base = _consolidate_knowledge(llm, knowledge_base, phase, phase_name)
        save_kb(knowledge_base, phase=phase)
        counter = 0
        log_colored("知识管理", "知识库整理完成。", Colors.MAGENTA)

    return {
        "knowledge_base": knowledge_base,
        "kb_consolidation_counter": counter,
        "added_count": added_count,
    }


def _consolidate_knowledge(llm, knowledge_base, phase, phase_name):
    """
    整理知识库：合并重复、更新过时信息、按类别归类。
    """
    if not knowledge_base:
        return knowledge_base

    kb_str = ""
    for i, entry in enumerate(knowledge_base):
        if isinstance(entry, dict):
            kb_str += f"{i+1}. [{entry.get('category', '?')}] {entry.get('content', '')}\n"
        else:
            kb_str += f"{i+1}. {entry}\n"

    system_prompt = f"""\
你是一个知识库整理专家。请整理以下知识库，执行以下操作：

1. 合并含义重复或相似的条目。
2. 将过时的信息标记为过时或删除。
3. 确保每条知识正确标注了类别 (input_triggered 或 spontaneous)。
4. 保持知识的准确性和简洁性。

当前阶段: {phase} - {phase_name}

当前知识库:
{kb_str}

严格以 JSON 格式输出：
{{
    "reasoning": "整理思路...",
    "consolidated_entries": [
        {{"content": "整理后的知识...", "category": "input_triggered 或 spontaneous"}}
    ]
}}
"""
    def validator(res):
        return isinstance(res, dict) and "consolidated_entries" in res

    result = llm.call_with_retry(system_prompt, "请整理知识库。", json_mode=True, validator=validator)

    entries = result.get("consolidated_entries", [])
    if entries:
        valid_entries = [
            {"content": e.get("content", ""), "category": e.get("category", "unknown")}
            for e in entries
            if isinstance(e, dict) and e.get("content")
        ]
        if valid_entries:
            log_colored("知识管理", f"整理后知识库: {len(knowledge_base)} -> {len(valid_entries)} 条", Colors.MAGENTA)
            return valid_entries

    return knowledge_base


def act(state: AgentState) -> dict:
    """
    行动节点：发送 Payload 到服务器，更新交互历史。
    """
    client = state["client"]
    payload = state.get("payload", "")
    history = list(state.get("history", []))  # 拷贝
    server_output_clean = state.get("server_output_clean", "")

    if payload:
        log_colored("客户端", f"发送：{payload}", Colors.GREEN)
        if client.send(payload):
            history.append(f"In: {payload} | Out: {server_output_clean[:50]}...")
        else:
            # 发送失败 → 触发重连
            return {
                "history": history,
                "should_reconnect": True,
            }
    else:
        log_colored("分析", "决定不发送任何内容。", Colors.CYAN)

    # 节奏控制
    time.sleep(1)

    return {
        "history": history,
        "should_reconnect": False,
    }


# ============================================================
#  并行知识管理节点
# ============================================================

def _run_knowledge_update_in_bg(state_snapshot: dict) -> dict:
    """
    在后台线程中执行知识管理逻辑。
    接收 state 的快照（纯数据），返回知识库更新结果。
    """
    # 构建一个伪 state 供 manage_knowledge 使用
    result = manage_knowledge(state_snapshot)
    return result


def start_knowledge_update_bg(state: AgentState) -> dict:
    """
    后台启动知识管理节点。
    
    在 observe 之后立即调用，将 manage_knowledge 提交到后台线程池，
    然后立即返回，不阻塞 analyze 和 act 的执行。
    """
    # 创建 state 快照（只包含 manage_knowledge 需要的字段）
    state_snapshot = {
        "llm": state["llm"],
        "history": list(state.get("history", [])),
        "knowledge_base": list(state.get("knowledge_base", [])),
        "phase": state.get("phase", 1),
        "phase_name": state.get("phase_name", "未知"),
        "tasks": list(state.get("tasks", [])),
        "kb_consolidation_counter": state.get("kb_consolidation_counter", 0),
        "server_output_clean": state.get("server_output_clean", ""),
    }

    future = _kb_executor.submit(_run_knowledge_update_in_bg, state_snapshot)
    # log_colored("知识管理", "后台知识更新已启动", Colors.MAGENTA)

    return {"kb_update_future": future}


def sync_knowledge_update(state: AgentState) -> dict:
    """
    同步知识管理结果节点。
    
    在 act 之后调用，等待后台知识管理线程完成，
    将更新后的知识库合并到 state 中。
    """
    future = state.get("kb_update_future")

    if future is None or not isinstance(future, Future):
        log_colored("知识管理", "无后台知识更新任务", Colors.RESET)
        return {"kb_update_future": None}

    if not future.done():
        # log_colored("知识管理", "等待后台知识更新完成...", Colors.YELLOW)
        pass

    try:
        result = future.result(timeout=120)  # 最多等待 120 秒
        kb = result.get("knowledge_base", state.get("knowledge_base", []))
        counter = result.get("kb_consolidation_counter", state.get("kb_consolidation_counter", 0))
        added_count = result.get("added_count", 0)
        
        if added_count > 0:
            log_colored("知识管理", f"后台知识更新已同步（新增 {added_count} 条）", Colors.MAGENTA)
            
        return {
            "knowledge_base": kb,
            "kb_consolidation_counter": counter,
            "kb_update_future": None,
        }
    except Exception as e:
        log_colored("知识管理", f"后台知识更新失败: {e}", Colors.RED)
        return {"kb_update_future": None}
