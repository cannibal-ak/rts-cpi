#!/bin/bash
# Cron-friendly wrapper around auto_ingest.py.
# Logs to /home/ankitprajapati/CPI/logs/auto_ingest.log.
set -u
cd /home/ankitprajapati/CPI
mkdir -p /home/ankitprajapati/CPI/logs
python3 apps/api/scripts/auto_ingest.py \
    --inbox /home/ankitprajapati/CPI/apps/api/data/inbox \
    >> /home/ankitprajapati/CPI/logs/auto_ingest.log 2>&1
