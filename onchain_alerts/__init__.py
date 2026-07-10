"""EVM block tailer and alert dispatcher."""

from onchain_alerts.config import Config, load_config
from onchain_alerts.watcher import BlockWatcher
from onchain_alerts.matcher import Matcher

__version__ = "0.2.1"
__all__ = ["Config", "load_config", "BlockWatcher", "Matcher"]
