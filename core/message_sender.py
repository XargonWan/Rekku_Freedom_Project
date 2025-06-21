async def send_content(bot, chat_id, message, content_type, message_id=None):
    try:
        kwargs = {"chat_id": chat_id}
        if message_id:
            kwargs["reply_to_message_id"] = message_id

        if content_type == "sticker" and message.sticker:
            await bot.send_sticker(**kwargs, sticker=message.sticker.file_id)
        elif content_type == "photo" and message.photo:
            await bot.send_photo(**kwargs, photo=message.photo[-1].file_id, caption=message.caption)
        elif content_type == "audio" and (message.audio or message.voice):
            audio = message.audio or message.voice
            await bot.send_audio(**kwargs, audio=audio.file_id, caption=message.caption)
        elif content_type == "file" and message.document:
            await bot.send_document(**kwargs, document=message.document.file_id, caption=message.caption)
        elif content_type == "video" and message.video:
            await bot.send_video(**kwargs, video=message.video.file_id, caption=message.caption)
        else:
            return False, f"\u274c Il contenuto ricevuto non corrisponde a {content_type.upper()}."

        return True, "\u2705 Risposta inviata."
    except Exception as e:
        return False, f"\u274c Errore durante l'invio: {e}"
    
def detect_media_type(message):
    if message.sticker:
        return "sticker"
    elif message.photo:
        return "photo"
    elif message.audio or message.voice:
        return "audio"
    elif message.video:
        return "video"
    elif message.document:
        return "file"
    return "unknown"
