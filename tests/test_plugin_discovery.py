#!/usr/bin/env python3
"""
Test per verificare che il MessagePlugin venga trovato correttamente.
"""

print("Testing MessagePlugin discovery...")

# Simulazione del MessagePlugin
class MockMessagePlugin:
    def get_supported_action_types(self):
        return ["message_telegram_bot", "message_reddit", "message_discord", "message_x"]
    
    def get_supported_actions(self):
        return {}  # Questo è il problema - dict vuoto

def test_plugin_discovery():
    """Test della logica di ricerca plugin."""
    plugin = MockMessagePlugin()
    action_type = "message_telegram_bot"
    
    print(f"Testing action type: {action_type}")
    
    # Logica VECCHIA (problematica)
    print("\n--- OLD Logic (problematic) ---")
    if hasattr(plugin, "get_supported_actions"):
        supported = plugin.get_supported_actions()
        print(f"get_supported_actions(): {supported}")
        print(f"'{action_type}' in supported: {action_type in supported}")
    elif hasattr(plugin, "get_supported_action_types"):
        supported = plugin.get_supported_action_types()
        print(f"get_supported_action_types(): {supported}")
        print(f"'{action_type}' in supported: {action_type in supported}")
    
    # Logica NUOVA (corretta)
    print("\n--- NEW Logic (fixed) ---")
    supported = None
    
    # Prefer get_supported_action_types if it returns a non-empty result
    if hasattr(plugin, "get_supported_action_types"):
        supported = plugin.get_supported_action_types()
        print(f"get_supported_action_types(): {supported}")
        if supported:  # Non-empty list/set/tuple
            print("Using action_types result")
        else:
            supported = None  # Try the other method
            print("action_types empty, trying actions")
    
    # Fallback to get_supported_actions if action_types is empty or doesn't exist
    if supported is None and hasattr(plugin, "get_supported_actions"):
        supported = plugin.get_supported_actions()
        print(f"get_supported_actions(): {supported}")
        print("Using actions result")
    
    if supported is not None:
        result = action_type in supported
        print(f"Final result: '{action_type}' in {supported} = {result}")
    else:
        print("No supported actions found")

if __name__ == "__main__":
    test_plugin_discovery()
