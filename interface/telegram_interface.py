from core.interface_loader import register_interface


class TelegramHandler:
    async def send(self, action_type, payload, source_message):
        """Handle sending actions via Telegram."""
        if action_type != "message":
            return
        bot = getattr(source_message, "_bot", None)
        if bot is None:
            return
        await bot.send_message(
            chat_id=payload.get("target"),
            text=payload.get("content", ""),
            reply_to_message_id=payload.get("reply_to"),
        )

    def get_target_string(self, chat_id):
        return f"telegram/{chat_id}"


register_interface("telegram", TelegramHandler())
