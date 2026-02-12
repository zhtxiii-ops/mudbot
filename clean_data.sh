#!/bin/bash

# 清除 task6 目录下的日志文件和知识库内容
echo "[*] 正在清理日志文件和知识库..."

# 删除日志文件
rm -f *.log 2>/dev/null

# 删除知识库文件和目录
rm -f knowledge_base.json 2>/dev/null
rm -rf knowledge_bases 2>/dev/null

# 重新创建知识库目录（可选，agent 启动时也会创建）
mkdir -p knowledge_bases

echo "[+] 清理完成。"
