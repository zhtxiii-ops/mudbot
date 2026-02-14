"""
Reflector Reflector Agent Module
Responsible for analyzing completed tasks, generating experiences and skills, and managing their persistence.
"""
import os
import json
import time
import datetime
from typing import List, Dict, Any

import config
from config import Colors
from nodes import log_colored

def _log_reflector(message: str, color: str = None):
    """Reflector dedicated logging"""
    log_colored("Reflector", message, color)
    
    # Write to file
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    formatted_msg = f"[{timestamp}] {message}\n"
    try:
        os.makedirs(os.path.dirname(config.REFLECTOR_LOG_FILE), exist_ok=True)
        with open(config.REFLECTOR_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted_msg)
    except Exception as e:
        print(f"Failed to write reflector log: {e}")

def _load_experiences() -> Dict[str, List[Dict]]:
    """Load experiences and skills from file"""
    if not os.path.exists(config.EXPERIENCES_FILE):
        return {"experiences": [], "skills": []}
    
    try:
        with open(config.EXPERIENCES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        _log_reflector(f"Error loading experiences: {e}", Colors.RED)
        return {"experiences": [], "skills": []}

def _save_experiences(data: Dict[str, List[Dict]]):
    """Save experiences and skills to file"""
    try:
        os.makedirs(config.REFLECTIONS_DIR, exist_ok=True)
        with open(config.EXPERIENCES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        _log_reflector(f"Error saving experiences: {e}", Colors.RED)

def reflect_on_task(llm: Any, task: Dict, knowledge_base: List[Dict], phase: int) -> Dict[str, List[Dict]]:
    """
    Reflect on a completed (or stuck) task.
    
    Args:
        llm: LLM client
        task: The task object (containing id, description, result, status)
        knowledge_base: Current knowledge base
        phase: Current phase number
        
    Returns:
        Dict containing new_experiences and new_skills
    """
    task_id = task.get("id", "unknown")
    task_status = task.get("status", "unknown")
    
    _log_reflector(f"Start reflecting on task [{task_id}] (Status: {task_status})", Colors.MAGENTA)
    
    # 1. Read task log
    log_path = os.path.join(config.TASK_LOG_DIR, f"{task_id}.log")
    if not os.path.exists(log_path):
        _log_reflector(f"Task log not found: {log_path}", Colors.RED)
        return {"new_experiences": [], "new_skills": []}
        
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            task_log_content = f.read()
    except Exception as e:
        _log_reflector(f"Failed to read task log: {e}", Colors.RED)
        return {"new_experiences": [], "new_skills": []}
        
    # 2. Load existing knowledge
    existing_data = _load_experiences()
    current_experiences = existing_data.get("experiences", [])
    current_skills = existing_data.get("skills", [])
    
    # 3. Construct Prompt
    existing_exp_str = json.dumps(current_experiences[-5:], indent=2, ensure_ascii=False) if current_experiences else "None"
    existing_skills_str = json.dumps([s["name"] for s in current_skills], indent=2, ensure_ascii=False) if current_skills else "None"
    
    system_prompt = f"""
You are an advanced AI Reflector. Your goal is to analyze the execution log of a task performed by an autonomous agent in a text-based environment (MUD) and distill valuable Experience and reusable Skills.

Task ID: {task_id}
Task Description: {task.get("description")}
Final Status: {task_status}
Result/Stuck Reason: {task.get("result", "N/A")}

Existing Skills: {existing_skills_str}

Your analysis should Focus on:
1. **Experience (Generic Lessons)**: What went wrong? What went right? What general usage patterns regarding the environment or commands were discovered? (e.g., "The 'look' command shows exits", "NPCs named 'Guard' block the way").
2. **Skills (Reusable Procedures)**: Identify specific, repeatable sequences of actions that achieved a sub-goal. A skill must have a clear Trigger (when to use) and Steps. (e.g., "Skill: Check Inventory", "Skill: Navigate to Town Square").

Input - Task Execution Log:
{task_log_content[-8000:]} 
(Log truncated if too long)

Output Requirements:
Strictly valid JSON format:
{{
    "new_experiences": [
        {{
            "summary": "One sentence summary",
            "lesson": "Detailed lesson learned",
            "tags": ["tag1", "tag2"]
        }}
    ],
    "new_skills": [
        {{
            "name": "Skill Name",
            "description": "What this skill does",
            "trigger": "When should this skill be used (context/conditions)",
            "steps": ["step 1", "step 2", "step 3"],
            "expected_outcome": "What happens after execution",
            "tags": ["tag1"]
        }}
    ]
}}

If no valuable experience or new skill is found, return empty lists. Do NOT duplicate existing skills unless you are improving them significantly.
    """

    # 4. Call LLM
    try:
        response = llm.call_with_retry(
            system_prompt, 
            "Please analyze the log and generate experiences and skills.",
            json_mode=True,
            model=config.REASONER_MODEL,
            caller_id="Reflector"
        )
    except Exception as e:
        _log_reflector(f"LLM call failed: {e}", Colors.RED)
        return {"new_experiences": [], "new_skills": []}

    new_experiences = response.get("new_experiences", [])
    new_skills = response.get("new_skills", [])
    
    # 5. Process and Save
    timestamp = datetime.datetime.now().isoformat()
    
    # Augment experiences
    for exp in new_experiences:
        exp["id"] = f"EXP-{int(time.time())}-{len(existing_data.get('experiences', []))}"
        exp["task_id"] = task_id
        exp["phase"] = phase
        exp["created_at"] = timestamp
        existing_data.setdefault("experiences", []).append(exp)
        _log_reflector(f"Generated Experience: {exp['summary']}", Colors.GREEN)

    # Augment skills
    for skill in new_skills:
        skill["id"] = f"SKILL-{int(time.time())}-{len(existing_data.get('skills', []))}"
        skill["source_task"] = task_id
        skill["created_at"] = timestamp
        existing_data.setdefault("skills", []).append(skill)
        _log_reflector(f"Generated Skill: {skill['name']}", Colors.GREEN)
        
    if new_experiences or new_skills:
        _save_experiences(existing_data)
        
    return {"new_experiences": new_experiences, "new_skills": new_skills}
