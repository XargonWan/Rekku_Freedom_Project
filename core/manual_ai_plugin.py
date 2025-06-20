# core/manual_ai_plugin.py

class ManualAIPlugin:
    def __init__(self):
        # key = trainer_message_id, value = {"chat_id", "message_id"}
        self.reply_map = {}

    def track_message(self, trainer_message_id, original_chat_id, original_message_id):
        self.reply_map[trainer_message_id] = {
            "chat_id": original_chat_id,
            "message_id": original_message_id
        }

    def get_target(self, trainer_message_id):
        return self.reply_map.get(trainer_message_id)

    def clear(self, trainer_message_id):
        if trainer_message_id in self.reply_map:
            del self.reply_map[trainer_message_id]
