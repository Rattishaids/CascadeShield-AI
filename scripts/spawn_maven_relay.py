"""Detach the optional official Maven relay without inheriting a caller's shell pipes."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
runtime = ROOT / '.runtime'
runtime.mkdir(exist_ok=True)
flags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == 'nt' else 0
with (runtime/'maven-relay.log').open('ab') as output, (runtime/'maven-relay-error.log').open('ab') as error:
    child = subprocess.Popen([sys.executable, str(ROOT/'scripts/maven_central_relay.py'),
                              '--bind', '0.0.0.0', '--port', '18090'],
                             cwd=ROOT, stdin=subprocess.DEVNULL, stdout=output, stderr=error,
                             close_fds=True, creationflags=flags, start_new_session=os.name != 'nt')
print(json.dumps({'pid': child.pid}))
