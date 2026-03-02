#!/bin/bash

# 清除 task6 目录下的日志文件和知识库内容
echo "[*] 正在清理日志文件和知识库..."

# 删除日志文件
# 删除日志文件及目录
rm -rf logs 2>/dev/null

# 删除知识库文件和目录
rm -rf data 2>/dev/null
# rm -f knowledge_base.json 2>/dev/null  <- No longer needed as they are in data/
# rm -rf knowledge_bases 2>/dev/null
# rm -rf reflections 2>/dev/null
# rm -rf test_env/reflections 2>/dev/null

echo "[+] 清理完成。"
