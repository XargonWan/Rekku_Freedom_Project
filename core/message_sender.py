from core import response_proxy, say_proxy
import core.plugin_instance as plugin_instance
import traceback
import os

# Sticker set used for custom Rekku emoji
TELEGRAM_STICKERS = os.getenv("TELEGRAM_STICKERS", "RekkuRetroDECKMascot")

async def send_rekku_sticker(bot, chat_id, emoji: str, reply_to_message_id=None):
    """Send a sticker from the configured set matching the given emoji."""

    print(f"[DEBUG/sticker] Searching for emoji '{emoji}' in set '{TELEGRAM_STICKERS}'")
    try:
        sticker_set = await bot.get_sticker_set(TELEGRAM_STICKERS)
        print(f"[DEBUG/sticker] Loaded {len(sticker_set.stickers)} stickers")
        for sticker in sticker_set.stickers:
            if sticker.emoji == emoji:
                print(f"[DEBUG/sticker] Found match: {sticker.file_id}")
                await bot.send_sticker(
                    chat_id=chat_id,
                    sticker=sticker.file_id,
                    reply_to_message_id=reply_to_message_id,
                )
                return
        print(f"[DEBUG/sticker] No sticker match for '{emoji}'")
    except Exception as e:
        print(f"[ERROR/sticker] Failed to load sticker set: {e}")

    # Fallback: send the raw emoji as plain text
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=emoji,
            reply_to_message_id=reply_to_message_id,
        )
    except Exception as e:
        print(f"[ERROR/sticker] Fallback text send failed for emoji '{emoji}': {e}")

async def send_content(bot, chat_id, message, content_type, reply_to_message_id=None):
    print(f"[DEBUG] Invio contenuto: {content_type}, reply_to={reply_to_message_id}")

    try:
        if content_type == "audio":
            try:
                print("[DEBUG] Invio audio in corso...")
                file_id = message.audio.file_id if message.audio else message.document.file_id
                print(f"[DEBUG] file_id rilevato: {file_id}")
                await bot.send_audio(chat_id=chat_id, audio=file_id, reply_to_message_id=reply_to_message_id)
                return True, "\u2705 Audio inviato con successo."
            except Exception as e_audio:
                print(f"[WARN] Invio audio fallito: {e_audio}")
                traceback.print_exc()
                if message.document:
                    try:
                        print("[DEBUG] Riprovo invio come documento (fallback)...")
                        await bot.send_document(chat_id=chat_id, document=message.document.file_id, reply_to_message_id=reply_to_message_id)
                        return True, "\u2705 Inviato come documento (fallback da audio)."
                    except Exception as e_fallback:
                        print(f"[ERROR] Anche il fallback documento � fallito: {e_fallback}")
                        traceback.print_exc()
                        return False, f"\u274c Errore doppio: {e_audio} / {e_fallback}"
                return False, f"\u274c Errore invio audio: {e_audio}"

        elif content_type == "document":
            try:
                print("[DEBUG] Invio documento in corso...")
                await bot.send_document(chat_id=chat_id, document=message.document.file_id, reply_to_message_id=reply_to_message_id)
                return True, "\u2705 Documento inviato con successo."
            except Exception as e_doc:
                print(f"[WARN] Invio documento fallito: {e_doc}")
                traceback.print_exc()
                mime = message.document.mime_type or ""
                filename = message.document.file_name or ""
                if mime.startswith("audio/") or filename.lower().endswith(".mp3"):
                    try:
                        print("[DEBUG] Riprovo invio come audio (fallback)...")
                        await bot.send_audio(chat_id=chat_id, audio=message.document.file_id, reply_to_message_id=reply_to_message_id)
                        return True, "\u2705 Inviato come audio (fallback da documento)."
                    except Exception as e_audio:
                        print(f"[ERROR] Anche il fallback audio � fallito: {e_audio}")
                        traceback.print_exc()
                        return False, f"\u274c Errore doppio: {e_doc} / {e_audio}"
                return False, f"\u274c Errore invio documento: {e_doc}"

        elif content_type == "voice":
            print("[DEBUG] Invio voice in corso...")
            await bot.send_voice(chat_id=chat_id, voice=message.voice.file_id, reply_to_message_id=reply_to_message_id)

        elif content_type == "photo":
            print("[DEBUG] Invio foto in corso...")
            await bot.send_photo(chat_id=chat_id, photo=message.photo[-1].file_id, reply_to_message_id=reply_to_message_id)

        elif content_type == "video":
            print("[DEBUG] Invio video in corso...")
            await bot.send_video(chat_id=chat_id, video=message.video.file_id, reply_to_message_id=reply_to_message_id)

        elif content_type == "sticker":
            print("[DEBUG] Invio sticker in corso...")
            await bot.send_sticker(chat_id=chat_id, sticker=message.sticker.file_id, reply_to_message_id=reply_to_message_id)

        elif content_type == "text":
            print("[DEBUG] Invio testo in corso...")
            await bot.send_message(chat_id=chat_id, text=message.text, reply_to_message_id=reply_to_message_id)

        elif content_type == "file":
            print("[DEBUG] Invio file in corso...")
            await bot.send_document(chat_id=chat_id, document=message.document.file_id, reply_to_message_id=reply_to_message_id)

        else:
            print(f"[ERROR] Tipo di contenuto non gestito: {content_type}")
            return False, "\u274c Tipo di contenuto non supportato."

        return True, "\u2705 Contenuto inviato con successo."

    except Exception as e:
        print(f"[ERROR] Errore nell'invio del contenuto: {e}")
        traceback.print_exc()
        return False, f"\u274c Errore: {e}"

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
    print(f"[DEBUG] Estrazione target per user_id={user_id}")

    # 1. Controllo via proxy (es. /photo, /say...)
    target = response_proxy.get_target(user_id)
    print(f"[DEBUG] Target iniziale da proxy: {target}")

    # 2. Risposta a messaggio
    if not target and message.reply_to_message:
        replied = message.reply_to_message
        print(f"[DEBUG] Risposta a messaggio: {replied.message_id}")
        print("[DEBUG] Verifica mapping nel plugin")

        for attempt in [replied.message_id,
                        getattr(replied.reply_to_message, "message_id", None)]:
            if attempt:
                tracked = plugin_instance.get_target(attempt)
                if tracked:
                    print(f"[DEBUG] Trovato target da reply: {tracked}")
                    return {
                        "chat_id": tracked["chat_id"],
                        "message_id": tracked["message_id"],
                        "type": detect_media_type(message)
                    }

    # 3. Fallback da /say
    if not target:
        chat_id = say_proxy.get_target(user_id)
        print(f"[DEBUG] Fallback target da /say: {chat_id}")
        if chat_id and chat_id != "EXPIRED":
            return {
                "chat_id": chat_id,
                "message_id": None,
                "type": detect_media_type(message)
            }

    print(f"[DEBUG] Target finale = {target}")
    return target


__all__ = [
    "send_content",
    "detect_media_type",
    "extract_response_target",
    "send_rekku_sticker",
]
