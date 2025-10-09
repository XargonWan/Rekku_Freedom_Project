import os
import signal
import sys
import subprocess
import asyncio
from core.db import init_db, test_connection, get_conn
# from core.blocklist import init_blocklist_table  # Now handled by blocklist plugin
from core.logging_utils import (
    log_debug,
    log_info,
    log_warning,
    setup_logging,
    log_error,
)


def cleanup_components():
    """Clean up all registered components (engines, plugins, interfaces)."""
    try:
        log_debug("[main] Starting component cleanup...")
        
        # Let the core initializer handle cleanup of all registered components
        from core.core_initializer import core_initializer
        
        # Cleanup LLM engines
        from core.llm_registry import get_llm_registry
        registry = get_llm_registry()
        for engine_name in registry.get_registered_engines():
            try:
                engine_instance = registry.get_engine_instance(engine_name)
                if engine_instance and hasattr(engine_instance, 'cleanup'):
                    engine_instance.cleanup()
                    log_debug(f"[main] Cleaned up engine: {engine_name}")
            except Exception as e:
                log_warning(f"[main] Failed to cleanup engine {engine_name}: {e}")
        
        log_info("[main] Component cleanup completed")
        
    except Exception as e:
        log_warning(f"[main] Component cleanup failed: {e}")


def signal_handler(signum, frame):
    """Handle termination signals gracefully."""
    log_info(f"[main] Received signal {signum}, shutting down gracefully...")
    
    # Clean up all components generically
    cleanup_components()
    
    log_info("[main] Shutdown complete")
    sys.exit(0)


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
        
        # Persist bootstrap configurations to DB after initialization
        log_debug("[main] Persisting bootstrap configurations...")
        from core.config_manager import config_registry
        await config_registry.persist_bootstrap_configs()
        log_debug("[main] Bootstrap configurations persisted")
        
        # Load all other configurations from DB
        log_debug("[main] Loading all configurations from DB...")
        await config_registry.load_all_from_db()
        log_debug("[main] All configurations loaded from DB")
        
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
        # Initialize core components - they will auto-discover and load all interfaces/plugins/engines
        try:
            log_info("[main] Initializing core components...")
            from core.core_initializer import core_initializer
            await core_initializer.initialize_all()
            log_info("[main] Core components initialized successfully")
            
            # Start message queue consumer
            from core import message_queue
            asyncio.create_task(message_queue.run())
            log_info("[main] Message queue consumer started")
        except Exception as e:
            log_error(f"[main] Critical error initializing core components: {repr(e)}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

        log_info("[main] All components auto-discovered and initialized")
        
        # 🎯 Display startup summary after all components are ready (this should be the last message)
        log_info("[main] All components initialized, displaying startup summary...")
        core_initializer.display_startup_summary()
        
        # Also display a quick resume even if some components are still loading
        resume = core_initializer.get_system_resume()
        log_info(f"[main] 🎯 QUICK STATUS: {resume['successful']}/{resume['total_components']} components loaded, {resume['total_actions']} actions available")
        
        # Keep the application running indefinitely
        log_info("[main] Application startup completed successfully - entering main loop")
        try:
            # Wait forever (or until interrupted)
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            log_info("[main] Received shutdown signal, exiting...")

    # Run the async application
    asyncio.run(start_application())
