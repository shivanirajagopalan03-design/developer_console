"""Run this console's production backend beside an existing frontend.

The installed Reflex CLI forwards the configured frontend port even in
backend-only mode. Omit it explicitly using the installed run implementation.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if __name__ == '__main__':
    from reflex.reflex import _run
    from reflex_base.constants import Env, RunningMode
    _run(env=Env.PROD, running_mode=RunningMode.BACKEND_ONLY, backend_port=8001)
