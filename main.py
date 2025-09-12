import os
import signal
import sys
import subprocess
import asyncio
from core.db import init_db, test_connection, get_conn
# from core.blocklist import init_blocklist_table  # Now handled by blocklist plugin
from core.config import get_active_llm
from core.logging_utils import (
    log_debug,
    log_info,
    log_warning,
    setup_logging,
    log_error,
)
from interface.reddit_interface import start_reddit_interface


def cleanup_chromium_processes():
    """Clean up any remaining Chromium processes and lock files while preserving login sessions."""
    try:
        # Kill Chromium processes
        log_debug("[main] Cleaning up Chromium processes...")
        subprocess.run(["pkill", "-f", "chromium"], capture_output=True, text=True)
        subprocess.run(["pkill", "-f", "chromedriver"], capture_output=True, text=True)
        
        # Clean up Chromium lock files and temp directories
        import tempfile
        import shutil
        import glob
        
        # Remove UC cache (safe to remove)
        uc_cache_dir = os.path.join(tempfile.gettempdir(), 'undetected_chromedriver')
        if os.path.exists(uc_cache_dir):
            shutil.rmtree(uc_cache_dir, ignore_errors=True)
            log_debug("[main] Removed undetected_chromedriver cache")
        
        # Remove Chromium lock files (preserves login data)
        profile_patterns = [
            os.path.expanduser("~/.config/chromium*"),
        ]
        
        for pattern in profile_patterns:
            for profile_dir in glob.glob(pattern):
                lock_files = [
                    os.path.join(profile_dir, "SingletonLock"),
                    os.path.join(profile_dir, "Default", "SingletonLock"),
                    os.path.join(profile_dir, "lockfile"),
                ]
                
                for lock_file in lock_files:
                    if os.path.exists(lock_file):
                        try:
                            os.remove(lock_file)
                            log_debug(f"[main] Removed lock file: {lock_file}")
                        except Exception as e:
                            log_warning(f"[main] Failed to remove lock file {lock_file}: {e}")
        
        # Remove only temporary profile directories (preserves persistent profiles)
        temp_patterns = [
            os.path.expanduser("~/.config/chromium-[0-9]*"),
            "/tmp/.org.chromium.*",
            "/tmp/chromium_*"
        ]
        
        for pattern in temp_patterns:
            for temp_dir in glob.glob(pattern):
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    log_debug(f"[main] Removed temporary directory: {temp_dir}")
                except Exception as e:
                    log_debug(f"[main] Could not remove {temp_dir}: {e}")
        
        log_info("[main] Chromium cleanup completed (login sessions preserved)")

    except Exception as e:
        log_warning(f"[main] Chromium cleanup failed: {e}")


def signal_handler(signum, frame):
    """Handle termination signals gracefully."""
    log_info(f"[main] Received signal {signum}, shutting down gracefully...")
    
    # Clean up Chromium processes
    cleanup_chromium_processes()
    
    # Stop the plugin if it has cleanup methods
    try:
        import core.plugin_instance as plugin_instance
        if hasattr(plugin_instance, 'plugin') and plugin_instance.plugin:
            if hasattr(plugin_instance.plugin, 'stop'):
                # Try async stop first
                try:
                    asyncio.run(plugin_instance.plugin.stop())
                    log_debug("[main] Plugin async stop completed")
                except RuntimeError as e:
                    if "already running" in str(e):
                        # Event loop already running, use sync cleanup
                        if hasattr(plugin_instance.plugin, 'cleanup'):
                            plugin_instance.plugin.cleanup()
                            log_debug("[main] Plugin sync cleanup completed")
                    else:
                        raise
            elif hasattr(plugin_instance.plugin, 'cleanup'):
                plugin_instance.plugin.cleanup()
                log_debug("[main] Plugin cleanup completed")
    except Exception as e:
        log_warning(f"[main] Plugin cleanup failed: {e}")
    
    log_info("[main] Shutdown complete")
    sys.exit(0)


async def initialize_core_components():
    """Initialize and log all core components."""
    log_info("[main] initialize_core_components() started")
    
    try:
        # Load and log active interfaces
        active_interfaces = ["telegram_bot", "telegram_userbot", "discord"]  # Example interfaces
        log_info("[main] Active interfaces initialized.")
        for interface in active_interfaces:
            log_info(f"[main] Active interface: {interface}")

        # Load and log plugins in ./plugins
        log_info("[main] Loading action plugins...")
        from core.action_parser import set_available_plugins, _load_action_plugins
        plugins = _load_action_plugins()
        if plugins:
            for plugin in plugins:
                log_info(f"[main] Loaded plugin: {plugin.__class__.__name__}")
        else:
            log_warning("[main] No plugins found in ./plugins.")

        # Pass the information to the action parser
        log_info("[main] Setting available plugins in action parser...")
        active_llm = await get_active_llm()
        log_info(f"[main] Active LLM: {active_llm}")
        set_available_plugins(active_interfaces, active_llm, [plugin.__class__.__name__ for plugin in plugins])
        log_info("[main] Core components initialization completed")
    except Exception as e:
        log_error(f"[main] Error in initialize_core_components(): {repr(e)}")
        raise


async def initialize_database():
    """Initialize database with proper async handling."""
    log_info("[main] initialize_database() started")
    
    # Verifica dei permessi dell'utente del database
    async def check_permissions():
        log_debug("[main] Checking database permissions...")
        conn = None
        try:
            conn = await get_conn()
            async with conn.cursor() as cur:
                await cur.execute("SHOW GRANTS FOR CURRENT_USER()")
                grants = await cur.fetchall()
                log_debug("[main] Database permissions check completed")
                return grants
        except Exception as e:
            log_error(f"[main] Error checking database permissions: {repr(e)}")
            raise
        finally:
            if conn:
                conn.close()

    try:
        grants = await check_permissions()
        log_info(f"[main] Database user permissions: {grants}")

        log_info("[main] Testing database connection...")
        if not await test_connection():
            log_error("[main] Database connection test failed")
            return False
        log_info("[main] Database connection test passed")
        
        log_info("[main] Initializing database schema...")
        await init_db()
        log_info("[main] Database schema initialized")
        
        # Blocklist table now handled by blocklist plugin
        # log_info("[main] Initializing blocklist table...")
        # await init_blocklist_table()
        # log_info("[main] Blocklist table initialized")
        
        log_info("[main] Database initialization completed successfully!")
        return True
    except Exception as e:
        log_error(f"[main] Error in initialize_database(): {repr(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Docker stop
    
    setup_logging()
    log_info("[main] Starting Rekku application...")
    
    # Clean up any leftover Chromium processes from previous runs
    cleanup_chromium_processes()
    
    # Test DB connectivity and initialize tables with retry mechanism
    import time
    max_retries = 30
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            log_info(f"[main] Attempting database connection (attempt {attempt + 1}/{max_retries})...")
            
            # Initialize database async
            if asyncio.run(initialize_database()):
                break
            else:
                raise Exception("Database initialization failed")
            
        except Exception as e:
            if attempt < max_retries - 1:
                log_warning(f"[main] Database connection attempt {attempt + 1} failed: {e}")
                log_info(f"[main] Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                log_error(f"[main] Critical error during database initialization after {max_retries} attempts: {e}")
                sys.exit(1)

    # 🌐 Show where the Webtop/VNC interface is available
    host = os.environ.get("WEBVIEW_HOST", "localhost")
    port = os.environ.get("WEBVIEW_PORT", "3000")
    log_info(f"[vnc] Webtop GUI available at: http://{host}:{port}")

    log_info("[main] Starting bot initialization...")
    
    async def start_application():
        # Initialize core components BEFORE starting the bot
        try:
            log_info("[main] Initializing core components...")
            from core.core_initializer import core_initializer
            await core_initializer.initialize_all()
            log_info("[main] Core components initialized successfully")
            # Start message queue consumer
            from core import message_queue
            asyncio.create_task(message_queue.run())
            log_info("[main] Message queue consumer started")
            # Start WebUI server
            from interface.webui import start_server
            asyncio.create_task(start_server())
            log_info("[main] WebUI server started")
        except Exception as e:
            log_error(f"[main] Critical error initializing core components: {repr(e)}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

        # 🎯 Display startup summary before starting bot (after all interfaces are initialized)
        log_info("[main] All components initialized, displaying startup summary...")
        core_initializer.display_startup_summary()

        # ✅ Start the bot
        try:
            from interface.telegram_bot import start_bot
            log_info("[main] Starting Telegram bot...")
            await start_bot()
            log_info("[main] Telegram bot started successfully")
        except Exception as e:
            log_error(f"[main] Critical error starting Telegram bot: {repr(e)}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    # Run the async application
    asyncio.run(start_application())

    log_info("[main] Application startup completed successfully")
