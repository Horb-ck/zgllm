#!/usr/bin/env bash
set -euo pipefail

BASE=/home/zgllm/workspace/elite_server

bash "$BASE/kill.sh"
bash "$BASE/run.sh"