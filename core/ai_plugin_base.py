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
