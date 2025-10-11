
# AGENTS.md

## Overview
Project name is "Synthetic Heart", stylized in "SyntH".
Synth is even the name given to the digital person "speicement" that this project is made for.

This project is structured around a **core** with modular components:
- **Core**: message chain, validation, dispatcher, DB, notifier. Includes automatic registration of validation rules from component actions.
- **Plugins**: provide actions (must register them via `get_supported_actions()` or delegate to interfaces). Sometimes called ActionPlugins. Some subclass `AIPluginBase` for LLM-like behavior.
- **LLM Engines**: interchangeable reasoning backends, implementing `AIPluginBase`.
- **Interfaces**: input/output handlers (e.g. Telegram, Discord). Register actions via `get_supported_actions()`.  

The **core must never hardcode plugin, LLM, or interface logic**.  
If a plugin/engine/interface is removed, the rest of the system should continue working.

---

## Core Principles
- All messages flow through a **single chain** managed by the core.  
- Actions must **attach to the existing chain**, not create new flows.  
- The **action parser** dynamically detects supported actions by querying plugins and interfaces.  
- Plugins are optional, but **useless if they don’t declare actions** (directly or via interfaces).  
- **Validation rules** are automatically registered from `get_supported_actions()` methods for backward compatibility.  

---

## Plugins
Each plugin must implement:
- `get_supported_actions()` → returns supported actions and their prompt instructions (or empty dict if delegating to interfaces).
- Optional hooks for initialization, teardown, or extended behavior.

Plugins can be:
- Standard plugins (subclass `PluginBase`): handle specific logic without LLM.
- AIPlugins (subclass `AIPluginBase`): handle actions with LLM-like behavior.

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
- Must not bypass the core's message chain.
- Should forward incoming data into the chain and dispatch core outputs.
- Register supported actions via `get_supported_actions()`.

---

## Testing
If you need to create some tsts please check the tests folder, do not create persistent tests outside that folder.
If you need a throwaway test instead the root is good but please delete it when you finished.

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

If you need to restar the dev container use:
```bash
cd /videodrome/videodrome-deployment/Synthetic_Heart/ && docker compose -f docker-compose-dev.yml --env-file .env-dev up -d --build && rm -rf logs/dev/* && videodrome synth restart dev
```
In this ay we thor away the old logs and we don't bother the stable deployment.

---

## Documentation
Everytime you do a change evaluate if itś needed to updated the documentation in ./docs.
The documentation must be written in English and in ReadTheDocs format.

---

## Notes

* Removing a plugin or engine should not break the system.
* Every action must integrate with the core.
* No direct, hardcoded coupling between the core and any specific plugin/interface/engine.
* Validation rules are auto-discovered from `get_supported_actions()` methods.