#!/bin/bash

# 定义日志文件
LOG_FILE="logs/system/runtime.log"

# 获取脚本所在目录
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 切换到脚本目录
cd "$DIR"

# 确保日志目录存在
mkdir -p logs/system

echo "[*] 正在启动 Agent (LangGraph)..."

# 后台运行 agent.py
# -u: 禁用 python 缓冲
# 2>&1: 合并 stderr 到 stdout
nohup /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 -u agent.py >> "$LOG_FILE" 2>&1 &

# 获取 PID
PID=$!

echo "[*] Agent 已在后台启动，PID: $PID"
echo "[*] 运行日志将写入: $DIR/$LOG_FILE"
echo "[*] 交互日志将写入: $DIR/logs/system/interaction.log"
echo "[*] 使用 'tail -f $LOG_FILE' 查看运行状态"
