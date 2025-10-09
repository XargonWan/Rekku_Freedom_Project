"""Central configuration registry that unifies environment, database and defaults.

This module exposes a singleton ``config_registry`` which components can use to
declare their configuration variables.  Each variable supports the following
precedence order when resolving its value:

1. Environment variable (strongest). When present it overrides the database
   value, is marked as read-only in the UI and is persisted back to the
   database for visibility.
2. Database value (persisted by the user through the Web UI or API).
3. Hard-coded default defined by the component. Falling back to the default
   emits a warning so operators know persistence failed.

Settings can be registered by the core, interfaces or LLM engines.  The registry
keeps metadata (label, description, component, whether a variable is advanced or
sensitive, etc.) so the Web UI can render a cohesive settings dashboard.

The registry offers synchronous ``get_value`` for modules that need to resolve
configuration during import time and asynchronous ``set_value`` for runtime
updates coming from the API/UI.  Updates trigger registered listeners so
components can reconfigure themselves immediately when possible.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Union

from core.logging_utils import log_debug, log_info, log_warning, log_error


ValueType = Union[type, Callable[[str], Any]]


@dataclass
class ConfigDefinition:
    key: str
    label: str
    description: str
    default: Any
    value_type: ValueType
    group: str
    component: str
    advanced: bool = False
    sensitive: bool = False
    tags: List[str] = field(default_factory=list)
    constraints: Optional[Dict[str, Any]] = None

    value: Any = None
    raw_value: Optional[str] = None
    env_override: bool = False
    env_value: Optional[str] = None
    loaded: bool = False
    listeners: List[Callable[[Any], None]] = field(default_factory=list)
    warned_default: bool = False


class ConfigRegistry:
    def __init__(self) -> None:
        self._definitions: Dict[str, ConfigDefinition] = {}
        self._load_lock = asyncio.Lock()
        self._pending_env_persists: Dict[str, str] = {}  # Buffer for env overrides to persist when DB is ready

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_value(
        self,
        key: str,
        default: Any,
        *,
        label: Optional[str] = None,
        description: str = "",
        value_type: ValueType = str,
        group: str = "core",
        component: str = "core",
        advanced: bool = False,
        sensitive: bool = False,
        tags: Optional[Iterable[str]] = None,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Return the typed value for ``key`` or register it if unknown."""

        definition = self._register_definition(
            key,
            default,
            label=label,
            description=description,
            value_type=value_type,
            group=group,
            component=component,
            advanced=advanced,
            sensitive=sensitive,
            tags=tags,
            constraints=constraints,
        )
        if not definition.loaded:
            self._load_definition_sync(definition)
        return definition.value

    async def set_value(self, key: str, new_value: Any) -> None:
        """Persist a new value for ``key`` and notify listeners."""

        definition = self._definitions.get(key)
        if definition is None:
            raise KeyError(f"Unknown configuration key: {key}")
        if definition.env_override:
            raise ValueError(
                f"Configuration '{key}' is overridden by environment and cannot be modified."
            )

        serialized = self._serialize_value(definition, new_value)
        typed_value = self._convert_value(definition, serialized)

        await self._persist_to_db(definition.key, serialized)

        definition.value = typed_value
        definition.raw_value = serialized
        definition.loaded = True

        log_info(f"[config] Updated '{key}' via Web UI/API")

        for callback in list(definition.listeners):
            try:
                callback(typed_value)
            except Exception as exc:  # pragma: no cover - listener safety
                log_warning(f"[config] Listener for '{key}' failed: {exc}")

    def add_listener(self, key: str, callback: Callable[[Any], None]) -> None:
        definition = self._definitions.get(key)
        if definition is None:
            raise KeyError(f"Unknown configuration key: {key}")
        definition.listeners.append(callback)

    async def flush_env_overrides_to_db(self) -> None:
        """Persist all buffered env override values to the database.
        
        This should be called once the database is ready during startup.
        """
        if not self._pending_env_persists:
            return
        
        log_info(f"[config] Flushing {len(self._pending_env_persists)} env override(s) to database")
        for key, value in list(self._pending_env_persists.items()):
            try:
                await self._persist_to_db(key, value)
                log_debug(f"[config] ✓ Persisted env override '{key}' to DB")
            except Exception as exc:
                log_warning(f"[config] Failed to persist env override '{key}': {exc}")
        
        self._pending_env_persists.clear()
        log_info("[config] ✓ Env overrides flushed to database")

    def export_definitions(self) -> List[Dict[str, Any]]:
        """Return all registered definitions with current state for the API."""

        exported: List[Dict[str, Any]] = []
        for defn in self._definitions.values():
            if not defn.loaded:
                try:
                    self._load_definition_sync(defn)
                except Exception as exc:
                    log_warning(f"[config] Failed to load '{defn.key}' during export: {exc}")

            exported.append(
                {
                    "key": defn.key,
                    "label": defn.label,
                    "description": defn.description,
                    "value": self._export_value(defn),
                    "default": self._export_default(defn),
                    "group": defn.group,
                    "component": defn.component,
                    "advanced": defn.advanced,
                    "sensitive": defn.sensitive,
                    "env_override": defn.env_override,
                    "value_type": self._type_name(defn.value_type),
                    "tags": list(defn.tags),
                    "constraints": defn.constraints,
                }
            )
        return sorted(exported, key=lambda item: (item["group"], item["component"], item["label"]))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _register_definition(
        self,
        key: str,
        default: Any,
        *,
        label: Optional[str],
        description: str,
        value_type: ValueType,
        group: str,
        component: str,
        advanced: bool,
        sensitive: bool,
        tags: Optional[Iterable[str]],
        constraints: Optional[Dict[str, Any]],
    ) -> ConfigDefinition:
        existing = self._definitions.get(key)
        if existing:
            return existing

        definition = ConfigDefinition(
            key=key,
            label=label or key,
            description=description,
            default=default,
            value_type=value_type,
            group=group,
            component=component,
            advanced=advanced,
            sensitive=sensitive,
            tags=list(tags or []),
            constraints=constraints,
        )
        self._definitions[key] = definition
        log_debug(f"[config] Registered setting '{key}' (component={component})")
        return definition

    def _load_definition_sync(self, definition: ConfigDefinition) -> None:
        """Synchronously ensure ``definition`` is loaded."""

        env_value = os.getenv(definition.key)
        if env_value is not None:
            definition.env_override = True
            definition.env_value = env_value
            definition.raw_value = env_value
            definition.value = self._convert_value(definition, env_value)
            definition.loaded = True
            # Buffer env override for later persistence to DB
            self._pending_env_persists[definition.key] = env_value
            return

        raw_value: Optional[str] = None
        if "bootstrap" not in definition.tags:
            try:
                raw_value = self._load_from_db_sync(definition.key)
            except Exception as exc:
                # Use print to avoid circular import with logging_utils during initialization
                print(f"[config] Failed to load '{definition.key}' from DB: {exc}", flush=True)


        if raw_value is not None:
            definition.raw_value = raw_value
            definition.value = self._convert_value(definition, raw_value)
            definition.loaded = True
            return

        if not definition.warned_default:
            # Use print to avoid circular import with logging_utils during initialization
            print(
                f"[config] Using hard-coded default for '{definition.key}' ({definition.default!r})", 
                flush=True
            )
            definition.warned_default = True

        definition.value = definition.default
        definition.raw_value = self._serialize_value(definition, definition.default)
        definition.loaded = True
        
        # CRITICAL FIX: Don't persist default immediately if we skipped DB load
        # due to running event loop - the value might exist in DB but wasn't loaded yet.
        # Only persist if we're sure DB was checked (no running loop or bootstrap tag)
        try:
            loop = asyncio.get_running_loop()
            # Event loop is running - DB load was skipped, so DON'T persist default yet
            # It will be loaded properly via load_all_from_db() later
            print(f"[config] Skipping default persistence for '{definition.key}' (will load from DB async)", flush=True)
        except RuntimeError:
            # No event loop - safe to persist default now
            self._persist_background(definition.key, definition.raw_value)

    def _load_from_db_sync(self, key: str) -> Optional[str]:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No event loop running - safe to create one
            return asyncio.run(self._load_from_db(key))
        else:
            # Event loop is running - we cannot block it
            # Skip DB load during sync import phase
            log_debug(f"[config] Skipping DB load for '{key}' during async context (will use default)")
            return None

    async def _load_from_db(self, key: str) -> Optional[str]:
        try:
            from core.db import get_conn, ensure_core_tables
        except ImportError as e:
            # Circular import during initialization - skip DB load
            print(f"[config] Skipping DB load for '{key}' during initialization: {e}", flush=True)
            return None

        await ensure_core_tables()
        conn = await get_conn()
        try:
            async with conn.cursor() as cur:
                await cur.execute("SELECT value FROM config WHERE config_key = %s", (key,))
                row = await cur.fetchone()
                if row:
                    return row[0]
        finally:
            conn.close()
        return None

    def _persist_background(self, key: str, value: str) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self._persist_to_db(key, value))
        else:
            loop.create_task(self._persist_to_db(key, value))

    async def _persist_to_db(self, key: str, value: str) -> None:
        try:
            from core.db import get_conn, ensure_core_tables
        except ImportError as e:
            # Circular import during initialization - skip DB persist
            print(f"[config] Skipping DB persist for '{key}' during initialization: {e}", flush=True)
            return

        await ensure_core_tables()
        conn = await get_conn()
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    "REPLACE INTO config (config_key, value) VALUES (%s, %s)",
                    (key, value),
                )
                await conn.commit()
        finally:
            conn.close()

    def _serialize_value(self, definition: ConfigDefinition, value: Any) -> str:
        if value is None:
            return ""
        if definition.value_type is bool:
            return "true" if bool(value) else "false"
        if definition.value_type is int:
            return str(int(value))
        if definition.value_type is float:
            return str(float(value))
        if callable(definition.value_type) and definition.value_type not in (bool, int, float, str):
            converted = definition.value_type(value)
            return str(converted)
        return str(value)

    def _convert_value(self, definition: ConfigDefinition, raw_value: str) -> Any:
        try:
            if definition.value_type is bool:
                return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}
            if definition.value_type is int:
                return int(raw_value)
            if definition.value_type is float:
                return float(raw_value)
            if callable(definition.value_type) and definition.value_type not in (bool, int, float, str):
                return definition.value_type(raw_value)
        except Exception as exc:
            # Use print to avoid circular import with logging_utils during initialization
            print(f"[config] Failed to cast '{definition.key}' value '{raw_value}' ({exc}), using default", flush=True)
            return definition.default
        if definition.value_type is str:
            if raw_value == "" and definition.default is None:
                return None
            return raw_value
        return raw_value

    def _export_value(self, definition: ConfigDefinition) -> Any:
        if definition.value_type is bool:
            return bool(definition.value)
        if definition.value_type in (int, float):
            return definition.value
        return "" if definition.value is None else str(definition.value)

    def _export_default(self, definition: ConfigDefinition) -> Any:
        if definition.value_type is bool:
            return bool(definition.default)
        if definition.value_type in (int, float):
            return definition.default
        return "" if definition.default is None else str(definition.default)

    def _type_name(self, value_type: ValueType) -> str:
        if value_type is bool:
            return "bool"
        if value_type is int:
            return "int"
        if value_type is float:
            return "float"
        return "str"

    async def persist_bootstrap_configs(self) -> None:
        """
        Persist all bootstrap configurations to the database after DB initialization.
        
        This is called after the database is ready to ensure bootstrap configs
        (like DB_HOST, DB_PORT, etc.) that were loaded from environment variables
        are visible in the UI.
        """
        for definition in self._definitions.values():
            if "bootstrap" in definition.tags and definition.env_override and definition.loaded:
                try:
                    await self._persist_to_db(definition.key, definition.raw_value)
                    log_debug(f"[config] Persisted bootstrap config '{definition.key}' to DB")
                except Exception as exc:
                    log_warning(f"[config] Failed to persist bootstrap config '{definition.key}': {exc}")

    async def load_all_from_db(self) -> None:
        """
        Load all non-bootstrap configurations from the database.
        
        This is called after DB initialization to load configurations that were
        skipped during module imports (when running inside an async context).
        
        CRITICAL: This fixes the issue where removing env variables causes configs
        to be lost. When a variable is removed from ENV, this function ensures the
        DB value is loaded instead of using defaults.
        """
        loaded_count = 0
        for definition in self._definitions.values():
            # Skip bootstrap configs (already loaded from env)
            if "bootstrap" in definition.tags:
                continue
            
            # Skip if already loaded from environment
            if definition.env_override:
                continue
                
            # Skip if already properly loaded from DB (has raw_value)
            if definition.loaded and definition.raw_value is not None and definition.raw_value != "":
                continue
            
            try:
                raw_value = await self._load_from_db(definition.key)
                if raw_value is not None:
                    definition.raw_value = raw_value
                    definition.value = self._convert_value(definition, raw_value)
                    definition.loaded = True
                    loaded_count += 1
                    log_debug(f"[config] ✓ Loaded '{definition.key}' from DB: {raw_value}")
                else:
                    # Use default value if not in DB and persist it
                    if not definition.loaded:
                        definition.value = definition.default
                        definition.raw_value = self._serialize_value(definition, definition.default)
                        definition.loaded = True
                        # Persist default to DB
                        await self._persist_to_db(definition.key, definition.raw_value)
                        log_debug(f"[config] Persisted default for '{definition.key}' to DB")
            except Exception as exc:
                log_warning(f"[config] Failed to load '{definition.key}' from DB: {exc}")
        
        if loaded_count > 0:
            log_info(f"[config] ✓ Loaded {loaded_count} configuration(s) from database")


config_registry = ConfigRegistry()
