class AIPluginBase:
    def track_message(self, trainer_message_id, original_chat_id, original_message_id):
        raise NotImplementedError()

    def get_target(self, trainer_message_id):
        raise NotImplementedError()

    def clear(self, trainer_message_id):
        raise NotImplementedError()

    async def generate_response(self, messages):
        raise NotImplementedError()
