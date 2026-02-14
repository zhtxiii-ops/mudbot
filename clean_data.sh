#!/bin/bash

# 清除 task6 目录下的日志文件和知识库内容
echo "[*] 正在清理日志文件和知识库..."

# 删除日志文件
rm -f agent_interaction.log 2>/dev/null
rm -f agent_runtime.log 2>/dev/null
rm -f planner_history.log 2>/dev/null
rm -f knowledge_manager.log 2>/dev/null

# 删除知识库文件和目录
rm -f knowledge_base.json 2>/dev/null
rm -rf knowledge_bases 2>/dev/null
rm -rf task_logs 2>/dev/null

echo "[+] 清理完成。"
