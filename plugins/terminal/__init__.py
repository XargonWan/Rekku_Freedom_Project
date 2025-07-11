from core.plugin_base import PluginBase
from core.logging_utils import log_debug, log_info, log_warning, log_error


class ExamplePlugin(PluginBase):
    """A sample plugin used for demonstration."""

    def start(self):
        log_info("[example_plugin] started")

    def stop(self):
        log_info("[example_plugin] stopped")

    def get_metadata(self) -> dict:
        return {
            "name": "ExamplePlugin",
            "description": "Sample plugin for the Rekku project",
            "version": "0.1",
        }


PLUGIN_CLASS = ExamplePlugin
