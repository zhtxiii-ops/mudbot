"""
规划者节点模块
独立于执行循环之外，只负责：制定阶段任务、分配当前任务、推进阶段。
不参与 observe/analyze/act/manage_knowledge 循环。
"""
import json
import os
import config
from config import Colors
from state import AgentState


from nodes import log_colored, get_aggregated_kb


def _log(tag: str, message: str, color: str = None):
    """复用日志函数"""
    log_colored(tag, message, color)


# ============================================================
#  第一阶段固定任务
# ============================================================

PHASE1_TASKS = [
    {
        "id": "P1-T1",
        "description": "观察服务器的初始输出，判断这个socket连接是否基于文本的交互环境。"
                       "如果收到二进制数据或无法解码的内容，则判定为非文本环境。",
        "status": "pending",
        "result": None,
    },
    {
        "id": "P1-T2",
        "description": "如果确认是文本环境，进一步分析这是什么类型的交互环境。"
                       "可能的类型包括：文字MUD游戏、聊天系统、Linux Shell、"
                       "大模型问答接口、BBS论坛、或其他类型。"
                       "根据文本的格式、提示符、欢迎信息等特征进行判断。",
        "status": "pending",
        "result": None,
    },
]


# ============================================================
#  规划者节点
# ============================================================

def planner(state: AgentState) -> dict:
    """
    规划者节点：独立于执行循环之外的调度中心。
    
    只负责：
    1. 制定当前阶段的任务列表
    2. 从任务列表选取下一个待执行任务并制定计划
    3. 在阶段任务全部完成时推进到下一阶段
    
    不参与观察、分析、行动、知识管理的循环。
    """
    llm = state["llm"]
    phase = state.get("phase", 1)
    phase_name = state.get("phase_name", "环境识别")
    tasks = state.get("tasks", [])
    completed_phases = list(state.get("completed_phases", []))
    knowledge_base = state.get("knowledge_base", [])
    environment_type = state.get("environment_type", "unknown")
    history = state.get("history", [])

    _log("规划者", f"=== 阶段 {phase}: {phase_name} ===", Colors.BLUE)

    # ------------------------------------------------------------------
    # 步骤1：如果没有任务列表，制定当前阶段任务
    # ------------------------------------------------------------------
    if not tasks:
        if phase == 1:
            tasks = [dict(t) for t in PHASE1_TASKS]  # 深拷贝
            _log("规划者", f"第一阶段固定任务已加载（{len(tasks)}个任务）", Colors.BLUE)
        else:
            # 获取全量知识用于规划
            full_kb = get_aggregated_kb(phase, knowledge_base)
            tasks = _generate_phase_tasks(
                llm, phase, completed_phases, full_kb, environment_type
            )
            _log("规划者", f"第{phase}阶段任务已生成（{len(tasks)}个任务）", Colors.BLUE)

    # ------------------------------------------------------------------
    # 步骤2：检查是否所有任务完成 → 推进阶段
    # ------------------------------------------------------------------
    all_done = all(t["status"] == "completed" for t in tasks)
    if all_done and tasks:
        _log("规划者", f"阶段 {phase} 所有任务已完成，准备推进到下一阶段。", Colors.BLUE)

        # 检查是否为非文本环境需要退出
        if environment_type == "non_text":
            _log("规划者", "检测到非文本交互环境，准备退出。", Colors.RED)
            return {
                "tasks": tasks,
                "current_task": {},
                "should_exit": True,
            }

        # 保存阶段摘要
        phase_summary = {
            "phase": phase,
            "name": phase_name,
            "tasks_summary": [
                {"id": t["id"], "description": t["description"][:80], "result": t.get("result", "")}
                for t in tasks
            ],
            "key_findings": _extract_key_findings(tasks),
        }
        completed_phases.append(phase_summary)

        # 推进到新阶段
        new_phase = phase + 1
        # 获取全量知识用于新阶段规划（当前阶段知识库尚未清空，加上之前的所有）
        full_kb_for_planning = get_aggregated_kb(phase, knowledge_base)
        
        new_phase_name = _determine_phase_name(llm, new_phase, completed_phases, full_kb_for_planning, environment_type)
        new_tasks = _generate_phase_tasks(llm, new_phase, completed_phases, full_kb_for_planning, environment_type)

        _log("规划者", f"进入阶段 {new_phase}: {new_phase_name}（{len(new_tasks)}个任务）", Colors.BLUE)

        # 选取新阶段的第一个任务
        first_task = new_tasks[0] if new_tasks else {}
        if first_task:
            # 此时 knowledge_base 即将清空，但制定计划时应使用之前的全量知识作为背景
            # 这里的 full_kb_for_planning 包含了直到上一阶段的所有知识
            plan = _create_execution_plan(llm, first_task, history, full_kb_for_planning, new_phase, new_phase_name)
            first_task["status"] = "in_progress"
            first_task["plan"] = plan
            _log("规划者", f"分配任务 [{first_task['id']}]: {first_task['description'][:60]}...", Colors.BLUE)

        return {
            "phase": new_phase,
            "phase_name": new_phase_name,
            "tasks": new_tasks,
            "current_task": dict(first_task) if first_task else {},
            "completed_phases": completed_phases,
            "task_completed": False,
            "knowledge_base": [],  # 新阶段开始，重置当前阶段知识库
        }

    # ------------------------------------------------------------------
    # 步骤3：选取下一个待执行任务，制定执行计划
    # ------------------------------------------------------------------
    next_task = None
    for t in tasks:
        if t["status"] == "pending":
            next_task = t
            break

    if next_task is None:
        _log("规划者", "没有可执行的任务。", Colors.YELLOW)
        return {"tasks": tasks, "current_task": {}, "task_completed": False}

    # 制定执行计划
    # 获取全量知识
    full_kb = get_aggregated_kb(phase, knowledge_base)
    plan = _create_execution_plan(llm, next_task, history, full_kb, phase, phase_name)
    next_task["status"] = "in_progress"
    next_task["plan"] = plan

    _log("规划者", f"分配任务 [{next_task['id']}]: {next_task['description'][:60]}...", Colors.BLUE)
    _log("规划者", f"执行计划: {plan[:100]}...", Colors.CYAN)

    return {
        "tasks": tasks,
        "current_task": dict(next_task),
        "task_completed": False,
    }


# ============================================================
#  内部辅助函数
# ============================================================

def _generate_phase_tasks(llm, phase, completed_phases, knowledge_base, environment_type):
    """由 LLM 推算新阶段的任务列表"""
    phases_str = ""
    for cp in completed_phases:
        phases_str += f"\n### 阶段 {cp['phase']}: {cp['name']}\n"
        for ts in cp.get("tasks_summary", []):
            phases_str += f"- [{ts['id']}] {ts['description']}: {ts.get('result', '无')}\n"
        phases_str += f"关键发现: {cp.get('key_findings', '无')}\n"

    kb_str = _format_kb(knowledge_base)

    system_prompt = f"""\
你是一个智能规划者。你的职责是根据已完成的工作和已有知识，为新阶段制定合理的任务列表。

环境类型: {environment_type}

已完成的阶段及任务（进度总结）:
{phases_str if phases_str else '无（这是第一个需要规划的阶段）'}

当前知识库（已获取的信息）:
{kb_str}

你的任务是：
1. 总结在这个特定的交互环境中，我们已经完成了什么，取得了什么成果。
2. 分析还有什么重要的目标没有完成。
3. 基于以上分析，推断第 {phase} 阶段应该执行的进阶任务。

任务要求：
- 进阶性：不要重复已完成的任务，要在已有基础上深入。
- 具体性：任务应该是具体的、可执行的、可验证的。
- 数量：每个阶段 2-5 个任务为宜。

严格以 JSON 格式输出：
{{
    "phase_name": "这个阶段的名称",
    "status_summary": "我们已经完成了X，取得了Y...",
    "gap_analysis": "还有Z没做...",
    "reasoning": "因此本阶段的重点是...",
    "tasks": [
        {{"id": "P{phase}-T1", "description": "任务描述..."}},
        {{"id": "P{phase}-T2", "description": "任务描述..."}}
    ]
}}
"""

    def validator(res):
        return isinstance(res, dict) and "tasks" in res and isinstance(res["tasks"], list)

    result = llm.call_with_retry(
        system_prompt, f"请为第 {phase} 阶段制定任务。",
        json_mode=True, validator=validator, model=config.REASONER_MODEL
    )

    tasks = []
    for t in result.get("tasks", []):
        tasks.append({
            "id": t.get("id", f"P{phase}-T?"),
            "description": t.get("description", ""),
            "status": "pending",
            "result": None,
        })
    return tasks


def _determine_phase_name(llm, phase, completed_phases, knowledge_base, environment_type):
    """由 LLM 决定新阶段的名称"""
    phases_str = ", ".join([f"阶段{cp['phase']}: {cp['name']}" for cp in completed_phases])

    system_prompt = f"""\
你是一个智能规划者。根据以下已完成的阶段，为第 {phase} 阶段命名。
环境类型: {environment_type}
已完成阶段: {phases_str if phases_str else '无'}

严格以 JSON 格式输出：
{{"phase_name": "简短的阶段名称"}}
"""
    result = llm.call_with_retry(
        system_prompt, f"请为第 {phase} 阶段命名。",
        json_mode=True, model=config.REASONER_MODEL
    )
    return result.get("phase_name", f"阶段{phase}")


def _create_execution_plan(llm, task, history, knowledge_base, phase, phase_name):
    """为具体任务制定执行计划（不依赖服务器输出，由规划者提前制定）"""
    # 注意：根据需求，制定计划时不需要最近交互历史
    kb_str = _format_kb(knowledge_base, limit=30)

    system_prompt = f"""\
你是一个任务规划专家。请为以下任务制定一个具体的执行计划。

当前阶段: {phase} - {phase_name}
任务: {task['description']}

知识库:
{kb_str}

请制定一个简明的执行计划，说明分析节点应该关注什么、期望什么结果、如何判断任务完成。

严格以 JSON 格式输出：
{{"plan": "具体的执行计划描述..."}}
"""
    result = llm.call_with_retry(
        system_prompt, f"请为任务 {task['id']} 制定执行计划。",
        json_mode=True, model=config.REASONER_MODEL
    )
    return result.get("plan", "观察服务器输出并做出适当响应。")


def _extract_key_findings(tasks):
    """从已完成任务中提取关键发现"""
    findings = []
    for t in tasks:
        if t.get("result"):
            findings.append(f"[{t['id']}] {t['result']}")
    return "; ".join(findings) if findings else "无"


def _format_kb(knowledge_base, limit=30):
    """格式化知识库为字符串"""
    if not knowledge_base:
        return "暂无。"
    kb_str = ""
    for entry in knowledge_base[-limit:]:
        if isinstance(entry, dict):
            kb_str += f"- [{entry.get('category', '?')}] {entry.get('content', '')}\n"
        else:
            kb_str += f"- {entry}\n"
    return kb_str
