#!/usr/bin/env bash
set -euo pipefail

BASE=/home/zgllm/workspace/elite_server
VENV=$BASE/new_py/elite11
LOGDIR=$BASE/logs

mkdir -p "$LOGDIR"
source "$VENV/bin/activate"

# 5002: Flask app (Gunicorn)
cd "$BASE"
nohup gunicorn -w 4 -b 0.0.0.0:5002 app:app \
  --access-logfile "$LOGDIR/app_access.log" \
  --error-logfile  "$LOGDIR/app_error.log" \
  >> "$LOGDIR/app_nohup.log" 2>&1 &
echo "5002 app started, pid=$!"

# 7000: KG service (Gunicorn)
cd "$BASE/KG"
nohup gunicorn -w 2 -b 0.0.0.0:7000 server:app \
  --access-logfile "$LOGDIR/kg_access.log" \
  --error-logfile  "$LOGDIR/kg_error.log" \
  >> "$LOGDIR/kg_nohup.log" 2>&1 &
echo "7000 KG started, pid=$!"

# 5001: MCP service (Uvicorn)
# 注意：mcp_server:mcp 需要能在当前工作目录的 Python 路径下被 import 到
cd "$BASE"
nohup python mcp_server.py >> "$LOGDIR/mcp_5001.log" 2>&1 &
echo "5001 MCP started, pid=$!"

sleep 1
ss -lntp | egrep ':5002|:7000|:5001' || true
