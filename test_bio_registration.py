#!/usr/bin/env python3

"""Test script per verificare la registrazione del BioPlugin"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_bio_plugin_registration():
    print("🔍 Testando la registrazione del BioPlugin...")
    
    # Import del plugin per attivare la registrazione
    from plugins.bio_manager import BioPlugin
    
    # Verifica del registry
    from core.core_initializer import PLUGIN_REGISTRY
    
    print(f"📦 Plugin registrati: {list(PLUGIN_REGISTRY.keys())}")
    
    if "bio_manager" in PLUGIN_REGISTRY:
        plugin = PLUGIN_REGISTRY["bio_manager"]
        print(f"✅ BioPlugin trovato nel registry: {plugin.__class__.__name__}")
        
        # Verifica dei metodi necessari
        if hasattr(plugin, "get_supported_action_types"):
            action_types = plugin.get_supported_action_types()
            print(f"🎯 Action types supportati: {action_types}")
        
        if hasattr(plugin, "get_supported_actions"):
            actions = plugin.get_supported_actions()
            print(f"🔧 Azioni supportate: {list(actions.keys())}")
            
        return True
    else:
        print("❌ BioPlugin NON trovato nel registry!")
        return False

if __name__ == "__main__":
    success = test_bio_plugin_registration()
    sys.exit(0 if success else 1)
