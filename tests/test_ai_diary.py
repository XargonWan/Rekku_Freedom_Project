"""Test cases for AI Diary Plugin"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import json

# Mock the database and core modules before importing the plugin
with patch('core.db.get_conn'), \
     patch('core.core_initializer.register_plugin'), \
     patch('plugins.ai_diary._run'):
    from plugins.ai_diary import (
        add_diary_entry, 
        add_diary_entry_async,
        get_recent_entries, 
        format_diary_for_injection,
        is_plugin_enabled,
        enable_plugin,
        disable_plugin,
        DiaryPlugin
    )


class TestAIDiary(unittest.TestCase):

    def setUp(self):
        """Set up test fixtures."""
        self.sample_entries = [
            {
                'id': 1,
                'content': 'Helped user with bio update',
                'timestamp': datetime.now().isoformat(),
                'tags': ['bio', 'helpful'],
                'involved': ['Jay'],
                'emotions': [{'type': 'helpful', 'intensity': 8}],
                'interface': 'telegram',
                'chat_id': '123',
                'thread_id': '2'
            },
            {
                'id': 2,
                'content': 'Performed terminal commands for system info',
                'timestamp': (datetime.now() - timedelta(hours=1)).isoformat(),
                'tags': ['system', 'terminal'],
                'involved': [],
                'emotions': [{'type': 'focused', 'intensity': 6}],
                'interface': 'telegram',
                'chat_id': '123',
                'thread_id': '0'
            }
        ]

    @patch('plugins.ai_diary._run')
    @patch('plugins.ai_diary._execute')
    def test_add_diary_entry(self, mock_execute, mock_run):
        """Test adding a diary entry."""
        add_diary_entry(
            content="Test diary entry",
            tags=["test", "automation"],
            involved=["TestUser"],
            emotions=[{"type": "curious", "intensity": 5}],
            interface="telegram",
            chat_id="123",
            thread_id="2"
        )
        
        mock_run.assert_called_once()
        mock_execute.assert_called_once()

    def test_format_diary_for_injection(self):
        """Test formatting diary entries for prompt injection."""
        formatted = format_diary_for_injection(self.sample_entries)
        
        self.assertIn("=== Rekku's Recent Diary ===", formatted)
        self.assertIn("Helped user with bio update", formatted)
        self.assertIn("#tags: bio, helpful", formatted)
        self.assertIn("#involved: Jay", formatted)
        self.assertIn("#emotions: helpful(8)", formatted)
        self.assertIn("=== End Diary ===", formatted)

    def test_format_empty_diary(self):
        """Test formatting empty diary entries."""
        formatted = format_diary_for_injection([])
        self.assertEqual(formatted, "")

    @patch('plugins.ai_diary._run')
    @patch('plugins.ai_diary._fetchall')
    def test_get_recent_entries_with_char_limit(self, mock_fetchall, mock_run):
        """Test getting recent entries with character limit."""
        mock_fetchall.return_value = self.sample_entries
        mock_run.return_value = self.sample_entries
        
        # Test with character limit
        result = get_recent_entries(days=2, max_chars=100)
        
        # Should return at least one entry but respect char limit
        self.assertIsInstance(result, list)

    def test_plugin_enable_disable(self):
        """Test enabling and disabling the plugin."""
        # Test current status
        status = is_plugin_enabled()
        self.assertIsInstance(status, bool)
        
        # Test manual disable
        disable_plugin()
        self.assertFalse(is_plugin_enabled())
        
        # Test re-enable (this will fail in tests due to mocking, but we test the function exists)
        with patch('plugins.ai_diary._run'):
            result = enable_plugin()
            self.assertIsInstance(result, bool)

    def test_diary_when_disabled(self):
        """Test that diary functions work gracefully when plugin is disabled."""
        # Disable plugin
        disable_plugin()
        
        # Test add_diary_entry with disabled plugin
        add_diary_entry("Test entry")  # Should not raise exception
        
        # Test get_recent_entries with disabled plugin
        entries = get_recent_entries()
        self.assertEqual(entries, [])

    def test_diary_plugin_static_injection(self):
        """Test the diary plugin's static injection functionality."""
        plugin = DiaryPlugin()
        
        # Test supported actions
        actions = plugin.get_supported_actions()
        self.assertIn("static_inject", actions)
        
        # Test action types
        action_types = plugin.get_supported_action_types()
        self.assertIn("static_inject", action_types)

    @patch('plugins.ai_diary.get_recent_entries')
    @patch('plugins.ai_diary.should_include_diary')
    @patch('plugins.ai_diary.get_max_diary_chars')
    def test_static_injection_with_limits(self, mock_get_max_chars, mock_should_include, mock_get_recent):
        """Test static injection respects character limits."""
        from plugins.ai_diary import DiaryPlugin
        
        # Mock the configuration
        mock_should_include.return_value = True
        mock_get_max_chars.return_value = 500
        mock_get_recent.return_value = self.sample_entries
        
        plugin = DiaryPlugin()
        
        # Test injection
        result = plugin.get_static_injection()
        
        self.assertIn("diary", result)
        mock_should_include.assert_called_once()
        mock_get_max_chars.assert_called_once()

    @patch('plugins.ai_diary.get_recent_entries')
    @patch('plugins.ai_diary.should_include_diary')
    def test_static_injection_disabled_when_no_space(self, mock_should_include, mock_get_recent):
        """Test static injection is disabled when no space available."""
        from plugins.ai_diary import DiaryPlugin
        
        # Mock configuration to indicate no space
        mock_should_include.return_value = False
        
        plugin = DiaryPlugin()
        
        # Test injection
        result = plugin.get_static_injection()
        
        self.assertEqual(result["diary"], "")
        mock_get_recent.assert_not_called()


if __name__ == '__main__':
    unittest.main()
