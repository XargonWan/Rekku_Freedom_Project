# core/plugin_base.py

class PluginBase:
    """Base class for non-LLM plugins."""

    def __init__(self, config=None):
        self.config = config or {}

    def start(self):
        """Optional initialization logic."""
        pass

    def stop(self):
        """Optional teardown logic."""
        pass

    def get_metadata(self) -> dict:
        """Return plugin metadata such as name, description and version."""
        raise NotImplementedError("get_metadata must be implemented by the plugin")
