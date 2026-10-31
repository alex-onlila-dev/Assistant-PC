import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis.config import load_config  # noqa: E402
from jarvis.core.context import ctx  # noqa: E402


@pytest.fixture(autouse=True)
def config():
    ctx.cfg = load_config()
    return ctx.cfg
