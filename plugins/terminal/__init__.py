from core.plugin_base import PluginBase


class ExamplePlugin(PluginBase):
    """A sample plugin used for demonstration."""

    def start(self):
        print("[example_plugin] started")

    def stop(self):
        print("[example_plugin] stopped")

    def get_metadata(self) -> dict:
        return {
            "name": "ExamplePlugin",
            "description": "Sample plugin for the Rekku project",
            "version": "0.1",
        }


PLUGIN_CLASS = ExamplePlugin
