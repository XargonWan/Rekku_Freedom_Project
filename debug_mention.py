#!/usr/bin/env python3
"""
Real-time mention testing utility.
Use this to debug mention detection issues in the running bot.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def inspect_bot_instance():
    """Inspect the current bot instance to understand its structure."""
    try:
        import core.plugin_instance as plugin_instance
        from interface.telegram_bot import BOT_TOKEN
        
        print("🔍 Bot Instance Inspection")
        print("=" * 40)
        
        # Try to get bot info
        try:
            from telegram import Bot
            bot = Bot(BOT_TOKEN)
            print(f"Bot token configured: {BOT_TOKEN[:10]}...")
            
            # Try to get bot info (this will fail if not in container)
            try:
                import asyncio
                
                async def get_bot_info():
                    try:
                        me = await bot.get_me()
                        print(f"Bot ID: {me.id}")
                        print(f"Bot username: {me.username}")
                        print(f"Bot first name: {me.first_name}")
                        return me
                    except Exception as e:
                        print(f"Failed to get bot info: {e}")
                        return None
                
                # Run the async function
                if hasattr(asyncio, 'run'):
                    bot_info = asyncio.run(get_bot_info())
                else:
                    print("Cannot run async code in this environment")
                    bot_info = None
                    
            except Exception as e:
                print(f"Error getting bot info: {e}")
                
        except ImportError:
            print("Telegram library not available (normal outside container)")
            
        print("\n📋 To test mention detection:")
        print("1. Run this script inside the Docker container")
        print("2. Check the bot logs for mention detection details")
        print("3. Look for '[mention]' and '[telegram_bot]' debug messages")
        
    except Exception as e:
        print(f"Error: {e}")

def test_config_values():
    """Test configuration values used for mention detection."""
    print("\n⚙️ Configuration Values")
    print("=" * 30)
    
    try:
        from core.config import BOT_USERNAME, BOT_TOKEN
        print(f"BOT_USERNAME: {BOT_USERNAME}")
        print(f"BOT_TOKEN configured: {bool(BOT_TOKEN)}")
    except Exception as e:
        print(f"Error loading config: {e}")

if __name__ == "__main__":
    inspect_bot_instance()
    test_config_values()
    
    print("\n🛠️ Debugging Tips:")
    print("- Enable debug logging to see mention detection details")
    print("- Check that BOT_USERNAME matches the actual bot username")
    print("- Ensure the bot has proper permissions in groups")
    print("- Test both @mention and reply-to-message scenarios")
