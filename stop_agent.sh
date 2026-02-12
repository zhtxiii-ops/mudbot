#!/bin/bash

echo "[*] 正在停止 Agent..."

# 查找并杀掉 agent.py 进程 (匹配 task6/agent.py 或 python.*agent.py)
# 使用 [a]gent.py 避免 grep 自身出现在结果中
PIDS=$(ps aux | grep '[a]gent.py' | awk '{print $2}')

if [ -z "$PIDS" ]; then
    echo "[*] 未找到运行中的 Agent 进程"
else
    for PID in $PIDS; do
        echo "[*] 正在终止进程: $PID"
        kill "$PID" 2>/dev/null
    done
    echo "[*] Agent 已停止"
fi
