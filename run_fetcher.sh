#!/bin/bash
while pgrep -f crawl_videos.py > /dev/null; do
    sleep 10
done
echo "=========================================" >> agent_run.log
echo "FETCHER START" >> agent_run.log
echo "=========================================" >> agent_run.log
./venv/bin/python -u fetch_missing_videos.py >> agent_run.log 2>&1
