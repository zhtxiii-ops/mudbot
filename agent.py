"""
MUD 自主智能体 - 主入口
基于 LangGraph 的 规划者驱动 + 阶段化架构。
"""
import os
import sys
import time

import config
from config import Colors
from connection_manager import SocketClient
from llm_client import LLMClient
from graph import build_graph
from nodes import log_colored, load_kb


def main():
    log_colored("系统", f"正在启动自主智能体，目标：{config.TARGET_IP}:{config.TARGET_PORT}", Colors.WHITE)

    # 初始化组件
    llm = LLMClient()
    client = SocketClient()

    # 确保知识库目录存在
    os.makedirs(config.KB_DIR, exist_ok=True)

    # 编译 LangGraph 图
    compiled_graph = build_graph()
    log_colored("系统", "LangGraph 状态图已编译", Colors.WHITE)

    while True:  # 外层重连循环
        try:
            # 尝试连接
            if not client.connect():
                print(f"{Colors.RED}[系统] 5秒后重试...{Colors.RESET}")
                time.sleep(5)
                continue

            # 构建初始状态（规划者驱动，无长期/短期目标）
            initial_state = {
                "client": client,
                "llm": llm,
                "server_output": "",
                "server_output_clean": "",
                "history": [],
                "knowledge_base": load_kb(phase=1),  # 加载阶段1知识库
                "phase": 1,
                "phase_name": "环境识别",
                "tasks": [],
                "current_task": {},
                "completed_phases": [],
                "environment_type": "unknown",
                "analysis": "",
                "payload": "",
                "should_reconnect": False,
                "should_stop": False,
                "should_exit": False,
                "task_completed": False,
                "kb_consolidation_counter": 0,
            }

            # 运行 LangGraph 图
            log_colored("系统", "开始规划者驱动循环...", Colors.WHITE)
            final_state = compiled_graph.invoke(initial_state)

            # 图退出 → 检查原因
            if final_state.get("should_stop", False):
                log_colored("系统", "智能体主动停止。", Colors.WHITE)
                break

            if final_state.get("should_exit", False):
                env_type = final_state.get("environment_type", "unknown")
                log_colored("系统", f"检测到非文本交互环境 ({env_type})，智能体退出。", Colors.YELLOW)
                break

            # 否则是 should_reconnect，进行重连
            log_colored("系统", "连接断开，5秒后重连...", Colors.YELLOW)
            time.sleep(5)

        except KeyboardInterrupt:
            print(f"\n{Colors.WHITE}[!] 用户中断。{Colors.RESET}")
            break
        except Exception as e:
            print(f"{Colors.RED}[!] 发生未捕获异常：{e}。5秒后重启...{Colors.RESET}")
            time.sleep(5)
        finally:
            client.disconnect()


if __name__ == "__main__":
    main()
