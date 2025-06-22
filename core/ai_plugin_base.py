class AIPluginBase:
    async def handle_incoming_message(self, bot, message, context_memory):
        """Elabora un messaggio utente (gruppo o privato)."""
        raise NotImplementedError()

    def get_target(self, trainer_message_id):
        raise NotImplementedError()

    def clear(self, trainer_message_id):
        raise NotImplementedError()

    async def generate_response(self, messages):
        raise NotImplementedError()

    def get_supported_models(self) -> list[str]:
        return ["gpt-3.5-turbo", "gpt-4", "gpt-4o"]
