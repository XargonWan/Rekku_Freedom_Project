import unittest

try:  # pragma: no cover - optional dependency
    from plugins.terminal import TerminalPlugin  # type: ignore
except Exception:
    TerminalPlugin = None


@unittest.skipIf(TerminalPlugin is None, "terminal plugin unavailable")
class TestTerminalPlugin(unittest.TestCase):
    def test_has_validate_payload(self):
        plugin = TerminalPlugin()
        self.assertTrue(callable(getattr(plugin, 'validate_payload', None)))
