import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis.config import DEFAULT_CONFIG, load_config  # noqa: E402
from jarvis.core.context import ctx  # noqa: E402


@pytest.fixture(autouse=True)
def config():
    # Toujours la config livrée : les tests ne dépendent pas de ~/.jarvis/config.yaml
    ctx.cfg = load_config(str(DEFAULT_CONFIG))
    return ctx.cfg
