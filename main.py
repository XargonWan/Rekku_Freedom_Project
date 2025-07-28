import os
import signal
import sys
import subprocess
import asyncio
from core.db import init_db, test_connection
from core.blocklist import init_blocklist_table
from core.config import get_active_llm
from core.logging_utils import (
    log_debug,
    log_info,
    log_warning,
    setup_logging,
    log_error,
)

# WORKAROUND, TODO: INVESTIGATE THIS
# Ensure /usr/share/novnc exists
novnc_path = "/usr/share/novnc"
if not os.path.exists(novnc_path):
    os.makedirs(novnc_path)
    with open(os.path.join(novnc_path, "vnc.html"), "w") as f:
        f.write("<!DOCTYPE html><html><head><title>noVNC</title></head><body><h1>noVNC placeholder</h1></body></html>")
    with open(os.path.join(novnc_path, "index.html"), "w") as f:
        f.write("index.html")
    print("[main] Created /usr/share/novnc with placeholder files")

def cleanup_chrome_processes():
    """Clean up any remaining Chrome processes and lock files while preserving login sessions."""
    try:
        # Kill Chrome processes
        log_debug("[main] Cleaning up Chrome processes...")
        subprocess.run(["pkill", "-f", "chrome"], capture_output=True, text=True)
        subprocess.run(["pkill", "-f", "chromedriver"], capture_output=True, text=True)
        
        # Clean up Chrome lock files and temp directories
        import tempfile
        import shutil
        import glob
        
        # Remove UC cache (safe to remove)
        uc_cache_dir = os.path.join(tempfile.gettempdir(), 'undetected_chromedriver')
        if os.path.exists(uc_cache_dir):
            shutil.rmtree(uc_cache_dir, ignore_errors=True)
            log_debug("[main] Removed undetected_chromedriver cache")
        
        # Remove Chrome lock files (preserves login data)
        profile_patterns = [
            os.path.expanduser("~/.config/google-chrome*"),
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
            os.path.expanduser("~/.config/google-chrome-[0-9]*"),
            "/tmp/.com.google.Chrome*",
            "/tmp/chrome_*"
        ]
        
        for pattern in temp_patterns:
            for temp_dir in glob.glob(pattern):
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    log_debug(f"[main] Removed temporary directory: {temp_dir}")
                except Exception as e:
                    log_debug(f"[main] Could not remove {temp_dir}: {e}")
        
        log_info("[main] Chrome cleanup completed (login sessions preserved)")
        
    except Exception as e:
        log_warning(f"[main] Chrome cleanup failed: {e}")


def signal_handler(signum, frame):
    """Handle termination signals gracefully."""
    log_info(f"[main] Received signal {signum}, shutting down gracefully...")
    
    # Clean up Chrome processes
    cleanup_chrome_processes()
    
    # Stop the plugin if it has cleanup methods
    try:
        import core.plugin_instance as plugin_instance
        if hasattr(plugin_instance, 'current_plugin') and plugin_instance.current_plugin:
            if hasattr(plugin_instance.current_plugin, 'cleanup'):
                plugin_instance.current_plugin.cleanup()
                log_debug("[main] Plugin cleanup completed")
    except Exception as e:
        log_warning(f"[main] Plugin cleanup failed: {e}")
    
    log_info("[main] Shutdown complete")
    sys.exit(0)


async def initialize_core_components():
    """Initialize and log all core components."""
    # Load and log active interfaces
    active_interfaces = ["telegram_bot", "telegram_userbot", "discord"]  # Example interfaces
    log_info("[main] Active interfaces initialized.")
    for interface in active_interfaces:
        log_info(f"[main] Active interface: {interface}")

    # Load and log plugins in ./plugins
    from core.action_parser import set_available_plugins, _load_action_plugins
    plugins = _load_action_plugins()
    if plugins:
        for plugin in plugins:
            log_info(f"[main] Loaded plugin: {plugin.__class__.__name__}")
    else:
        log_warning("[main] No plugins found in ./plugins.")

    # Pass the information to the action parser
    set_available_plugins(active_interfaces, await get_active_llm(), [plugin.__class__.__name__ for plugin in plugins])


if __name__ == "__main__":
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Docker stop
    
    setup_logging()
    
    # Clean up any leftover Chrome processes from previous runs
    cleanup_chrome_processes()
    
    # Test DB connectivity and initialize tables with retry mechanism
    import time
    max_retries = 30
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            log_info(f"[main] Attempting database connection (attempt {attempt + 1}/{max_retries})...")
            
            # Verifica dei permessi dell'utente del database
            async def check_permissions():
                from core.db import execute_query
                query = "SHOW GRANTS FOR CURRENT_USER;"
                grants = await execute_query(query)
                log_info(f"[main] Database user permissions: {grants}")

            asyncio.run(check_permissions())

            if not asyncio.run(test_connection()):
                log_error("[main] Database connection failed. Exiting.")
                sys.exit(1)
            asyncio.run(init_db())
            init_blocklist_table()
            log_info("[main] Database initialization completed successfully!")
            break
            
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

    # ✅ Start the bot
    from interface.telegram_bot import start_bot
    asyncio.run(start_bot())

    # Initialize and log all core components
    asyncio.run(initialize_core_components())
