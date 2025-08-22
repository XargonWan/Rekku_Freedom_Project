
# AGENTS.md

## Overview
This project is structured around a **core** with modular components:
- **Core**: message chain, validation, dispatcher, DB, notifier.
- **Plugins**: provide actions (must register them).
- **LLM Engines**: interchangeable reasoning backends, implementing `AIPluginBase`.
- **Interfaces**: input/output handlers (e.g. Telegram, Discord).  

The **core must never hardcode plugin, LLM, or interface logic**.  
If a plugin/engine/interface is removed, the rest of the system should continue working.

---

## Core Principles
- All messages flow through a **single chain** managed by the core.  
- Actions must **attach to the existing chain**, not create new flows.  
- The **action parser** dynamically detects supported actions by querying plugins.  
- Plugins are optional, but **useless if they don’t declare actions**.  

---

## Plugins
Each plugin must implement:
- `get_supported_actions()` → returns supported actions and their prompt instructions.
- Optional hooks for initialization, teardown, or extended behavior.

If a plugin is missing:
- Its actions are ignored.
- The rest of the system remains operational.

---

## LLM Engines
- Engines subclass `AIPluginBase`.
- They handle reasoning and output JSON actions.
- Interchangeable: multiple engines can coexist.

---

## Interfaces
- Interfaces manage I/O with external systems (Telegram, Discord, etc.).
- Must not bypass the core chain.
- Should forward incoming data into the chain and dispatch core outputs.

---

## Testing
To run tests locally, the agent may:
1. Create a Python virtual environment:
```bash
   python -m venv venv
   source venv/bin/activate
```

2. Install requirements:

```bash
   pip install -r requirements.txt
```
3. Run the test suite:

```bash
   ./run_tests.sh
```

---

## Notes

* Removing a plugin or engine should not break the system.
* Every action must integrate with the central message chain.
* No direct, hardcoded coupling between the core and any specific plugin/interface/engine.