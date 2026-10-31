"""Un seul cerveau, trois adaptateurs : choisit l'implémentation selon l'OS."""
import sys

from jarvis.os_adapters.base import OSAdapter


def get_adapter() -> OSAdapter:
    if sys.platform.startswith("win"):
        from jarvis.os_adapters.windows import WindowsAdapter
        return WindowsAdapter()
    if sys.platform == "darwin":
        from jarvis.os_adapters.macos import MacAdapter
        return MacAdapter()
    from jarvis.os_adapters.linux import LinuxAdapter
    return LinuxAdapter()
