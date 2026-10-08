#!/bin/bash
cd /opt/KiAgentHSLU
sudo pkill -f 'venv/bin/python -u run_weeks' || true
sleep 2
: > agent_run.log
nohup ./venv/bin/python -u run_weeks.py >> agent_run.log 2>&1 &
sleep 1
echo started
