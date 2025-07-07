from core import response_proxy, say_proxy
import core.plugin_instance as plugin_instance
import traceback

async def send_content(bot, chat_id, message, content_type, reply_to_message_id=None):
    print(f"[DEBUG] Sending content: {content_type}, reply_to={reply_to_message_id}")

    try:
        if content_type == "audio":
            try:
                print("[DEBUG] Sending audio...")
                file_id = message.audio.file_id if message.audio else message.document.file_id
                print(f"[DEBUG] Detected file_id: {file_id}")
                await bot.send_audio(chat_id=chat_id, audio=file_id, reply_to_message_id=reply_to_message_id)
                return True, "\u2705 Audio sent successfully."
            except Exception as e_audio:
                print(f"[WARN] Audio send failed: {e_audio}")
                traceback.print_exc()
                if message.document:
                    try:
                        print("[DEBUG] Retrying send as document (fallback)...")
                        await bot.send_document(chat_id=chat_id, document=message.document.file_id, reply_to_message_id=reply_to_message_id)
                        return True, "\u2705 Sent as document (audio fallback)."
                    except Exception as e_fallback:
                        print(f"[ERROR] Document fallback also failed: {e_fallback}")
                        traceback.print_exc()
                        return False, f"\u274c Double error: {e_audio} / {e_fallback}"
                return False, f"\u274c Audio send error: {e_audio}"

        elif content_type == "document":
            try:
                print("[DEBUG] Sending document...")
                await bot.send_document(chat_id=chat_id, document=message.document.file_id, reply_to_message_id=reply_to_message_id)
                return True, "\u2705 Document sent successfully."
            except Exception as e_doc:
                print(f"[WARN] Document send failed: {e_doc}")
                traceback.print_exc()
                mime = message.document.mime_type or ""
                filename = message.document.file_name or ""
                if mime.startswith("audio/") or filename.lower().endswith(".mp3"):
                    try:
                        print("[DEBUG] Retrying send as audio (fallback)...")
                        await bot.send_audio(chat_id=chat_id, audio=message.document.file_id, reply_to_message_id=reply_to_message_id)
                        return True, "\u2705 Sent as audio (document fallback)."
                    except Exception as e_audio:
                        print(f"[ERROR] Audio fallback also failed: {e_audio}")
                        traceback.print_exc()
                        return False, f"\u274c Double error: {e_doc} / {e_audio}"
                return False, f"\u274c Document send error: {e_doc}"

        elif content_type == "voice":
            print("[DEBUG] Sending voice...")
            await bot.send_voice(chat_id=chat_id, voice=message.voice.file_id, reply_to_message_id=reply_to_message_id)

        elif content_type == "photo":
            print("[DEBUG] Sending photo...")
            await bot.send_photo(chat_id=chat_id, photo=message.photo[-1].file_id, reply_to_message_id=reply_to_message_id)

        elif content_type == "video":
            print("[DEBUG] Sending video...")
            await bot.send_video(chat_id=chat_id, video=message.video.file_id, reply_to_message_id=reply_to_message_id)

        elif content_type == "sticker":
            print("[DEBUG] Sending sticker...")
            await bot.send_sticker(chat_id=chat_id, sticker=message.sticker.file_id, reply_to_message_id=reply_to_message_id)

        elif content_type == "text":
            print("[DEBUG] Sending text...")
            await bot.send_message(chat_id=chat_id, text=message.text, reply_to_message_id=reply_to_message_id)

        elif content_type == "file":
            print("[DEBUG] Sending file...")
            await bot.send_document(chat_id=chat_id, document=message.document.file_id, reply_to_message_id=reply_to_message_id)

        else:
            print(f"[ERROR] Unhandled content type: {content_type}")
            return False, "\u274c Unsupported content type."

        return True, "\u2705 Content sent successfully."

    except Exception as e:
        print(f"[ERROR] Error sending content: {e}")
        traceback.print_exc()
        return False, f"\u274c Error: {e}"

def detect_media_type(message):
    if message.sticker:
        return "sticker"
    elif message.photo:
        return "photo"
    elif message.voice:
        return "voice"
    elif message.audio:
        return "audio"
    elif message.video:
        return "video"
    elif message.document:
        mime = message.document.mime_type or ""
        filename = message.document.file_name or ""
        if mime.startswith("audio/") or filename.lower().endswith(".mp3"):
            print(f"[DEBUG] Documento rilevato come audio: mime={mime}, filename={filename}")
            return "audio"
        print(f"[DEBUG] Documento generico: mime={mime}, filename={filename}")
        return "document"
    elif message.text:
        return "text"
    return "unknown"


def extract_response_target(message, user_id):
    print(f"[DEBUG] Extracting target for user_id={user_id}")

    # 1. Check via proxy (e.g. /photo, /say...)
    target = response_proxy.get_target(user_id)
    print(f"[DEBUG] Initial target from proxy: {target}")

    # 2. Reply to a message
    if not target and message.reply_to_message:
        replied = message.reply_to_message
        print(f"[DEBUG] Reply to message: {replied.message_id}")
        print("[DEBUG] Checking mapping in plugin")

        for attempt in [replied.message_id,
                        getattr(replied.reply_to_message, "message_id", None)]:
            if attempt:
                tracked = plugin_instance.get_target(attempt)
                if tracked:
                    print(f"[DEBUG] Found target from reply: {tracked}")
                    return {
                        "chat_id": tracked["chat_id"],
                        "message_id": tracked["message_id"],
                        "type": detect_media_type(message)
                    }

    # 3. Fallback from /say
    if not target:
        chat_id = say_proxy.get_target(user_id)
        print(f"[DEBUG] Fallback target from /say: {chat_id}")
        if chat_id and chat_id != "EXPIRED":
            return {
                "chat_id": chat_id,
                "message_id": None,
                "type": detect_media_type(message)
            }

    print(f"[DEBUG] Final target = {target}")
    return target


__all__ = [
    "send_content",
    "detect_media_type",
    "extract_response_target"
]
