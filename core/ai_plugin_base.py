# core/ai_plugin_base.py

from abc import ABC, abstractmethod
from core.prompt_engine import build_prompt

class AIPluginBase(ABC):
    """
    Interfaccia base per tutti i motori AI.
    Ogni plugin (OpenAI, Claude, Manual, ecc.) deve implementarla.
    """

    @abstractmethod
    async def handle_incoming_message(self, bot, message, prompt):
        """Elabora un messaggio usando un prompt gi� costruito."""
        pass

    @abstractmethod
    def get_target(self, trainer_message_id):
        """
        Restituisce a chi appartiene un messaggio addestrativo (per proxy reply).
        """
        pass

    @abstractmethod
    def clear(self, trainer_message_id):
        """
        Rimuove riferimenti da proxy una volta esauriti.
        """
        pass

    @abstractmethod
    async def generate_response(self, messages):
        """
        Invia una lista di messaggi al motore LLM e riceve la risposta.
        """
        pass

    def get_supported_models(self) -> list[str]:
        """
        Facoltativo. Restituisce l\u2019elenco dei modelli disponibili.
        Overrideabile da chi ne ha bisogno.
        """
        return []
