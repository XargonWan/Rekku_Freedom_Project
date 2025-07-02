# core/ai_plugin_base.py

from core.prompt_engine import build_prompt

class AIPluginBase:
    """
    Interfaccia base per tutti i motori AI.
    Ogni plugin (OpenAI, Claude, Manual, ecc.) può implementare i metodi desiderati.
    """

    async def handle_incoming_message(self, bot, message, prompt):
        """Elabora un messaggio usando un prompt già costruito."""
        raise NotImplementedError("handle_incoming_message non implementato")

    def get_target(self, trainer_message_id):
        """Restituisce a chi appartiene un messaggio addestrativo."""
        return None  # Default: non fa nulla

    def clear(self, trainer_message_id):
        """Rimuove riferimenti da proxy una volta esauriti."""
        pass  # Default: non fa nulla

    async def generate_response(self, messages):
        """Invia messaggi al motore LLM e riceve la risposta."""
        raise NotImplementedError("generate_response non implementato")

    def get_supported_models(self) -> list[str]:
        """Opzionale. Restituisce l’elenco dei modelli disponibili."""
        return []

    def set_notify_fn(self, notify_fn):
        """Opzionale: aggiorna dinamicamente la funzione di notifica."""
        self.notify_fn = notify_fn
        