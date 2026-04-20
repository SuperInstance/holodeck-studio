#!/bin/bash
source ~/.bashrc
export GITHUB_TOKEN=$(grep GITHUB_TOKEN ~/.bashrc | head -1 | sed 's/.*=//' | tr -d "'" | tr -d '"')
# Set lookback to 15 min ago for cron use
python3 -c "
import json
from datetime import datetime, timezone, timedelta
state = {'last_check': (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat(), 'seen': {}}
open('/tmp/cocapn-mud/git_bridge_state.json','w').write(json.dumps(state))
"
python3 /tmp/cocapn-mud/git_bridge.py
