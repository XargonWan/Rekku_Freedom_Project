import json
import re
from collections.abc import Mapping, Sequence
from typing import Optional, Dict, Tuple
from core.logging_utils import log_debug, log_info, log_warning


def custom_json_encoder(obj):
    """Fallback encoder that converts objects to dictionaries or strings."""
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)


def dumps(data, **kwargs):
    """Serialize ``data`` to JSON using the custom encoder."""
    kwargs.setdefault("ensure_ascii", False)
    return json.dumps(data, default=custom_json_encoder, **kwargs)


def sanitize_for_json(obj):
    """Recursively convert objects into JSON-serializable structures."""
    if isinstance(obj, Mapping):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        return [sanitize_for_json(v) for v in obj]
    try:
        json.dumps(obj)
        return obj
    except TypeError:
        if hasattr(obj, "__dict__"):
            return sanitize_for_json(obj.__dict__)
        return str(obj)


def extract_json_from_text(text: str, return_metadata: bool = False) -> Optional[Dict]:
    """Extract the first valid JSON object or array from text.
    
    This function is smart enough to extract JSON even when LLMs (like Gemini) 
    add extra text before or after the JSON structure. It scans the entire text
    looking for valid JSON objects or arrays, ignoring any surrounding text.
    
    Args:
        text: The text to parse
        return_metadata: If True, returns (json_obj, metadata_dict) tuple
                        If False, returns just json_obj (backward compatible)
    
    Returns:
        If return_metadata=False: JSON object or None
        If return_metadata=True: (JSON object or None, metadata dict)
        
    Metadata dict contains:
        - 'had_errors': bool - True if parsing encountered errors
        - 'error_count': int - Number of parsing errors encountered
        - 'unparsed_content': str - Content that couldn't be parsed (if any)
        - 'recovered': bool - True if JSON was recovered after errors
        - 'had_extra_text': bool - True if text was found before or after JSON
    """
    metadata = {
        'had_errors': False,
        'error_count': 0,
        'unparsed_content': '',
        'recovered': False,
        'had_extra_text': False
    }
    
    if not text:
        return (None, metadata) if return_metadata else None
    
    # Try to clean up common markdown/formatting issues
    cleaned_text = text.strip()
    
    # Remove markdown code blocks if present
    if cleaned_text.startswith('```json'):
        cleaned_text = cleaned_text[7:]  # Remove ```json
        if cleaned_text.endswith('```'):
            cleaned_text = cleaned_text[:-3]  # Remove ```
        cleaned_text = cleaned_text.strip()
    elif cleaned_text.startswith('```'):
        cleaned_text = cleaned_text[3:]  # Remove ```
        if cleaned_text.endswith('```'):
            cleaned_text = cleaned_text[:-3]  # Remove ```
        cleaned_text = cleaned_text.strip()
    
    # Also try original text in case cleaning broke something
    texts_to_try = [cleaned_text, text.strip()]
    
    decoder = json.JSONDecoder()
    found_json = None
    
    for text_variant in texts_to_try:
        log_debug(f"[extract_json_from_text] Trying text variant (length: {len(text_variant)})")
        
        # Scan for JSON objects starting from each '{'
        object_start_indices = [i for i, char in enumerate(text_variant) if char == '{']
        if not object_start_indices:
            log_debug("[extract_json_from_text] No starting braces found in text variant")
            continue
            
        for start in object_start_indices:
            try:
                obj, obj_end = decoder.raw_decode(text_variant[start:])
                obj_end += start
                prefix = text_variant[:start].strip()
                suffix = text_variant[obj_end:].strip()
                if prefix or suffix:
                    metadata['had_extra_text'] = True
                    log_info(f"[extract_json_from_text] ✅ Extracted JSON from text with extra content (prefix: {len(prefix)} chars, suffix: {len(suffix)} chars)")
                    if prefix:
                        log_debug(f"[extract_json_from_text] Prefix text: {prefix[:100]}...")
                    if suffix:
                        log_debug(f"[extract_json_from_text] Suffix text: {suffix[:100]}...")
                    # Check if suffix looks like it could be corrupted JSON
                    if suffix and ('{' in suffix or '"type"' in suffix or '"actions"' in suffix):
                        metadata['unparsed_content'] = suffix
                        metadata['recovered'] = True
                        log_warning(f"[extract_json_from_text] ⚠️ Corrupted JSON detected - unparsed content contains JSON-like structures")
                # Return JSON even if there's extra content - actions can still be executed
                log_debug(f"[extract_json_from_text] Found valid JSON object: {type(obj)}")
                found_json = obj
                break
            except json.JSONDecodeError as e:
                log_debug(f"[extract_json_from_text] JSON decode error at position {start}: {e}")
                metadata['had_errors'] = True
                metadata['error_count'] += 1
                continue
        
        if found_json:
            break
            
        # Scan for JSON arrays starting from each '['
        array_start_indices = [i for i, char in enumerate(text_variant) if char == '[']
        for start in array_start_indices:
            try:
                obj, obj_end = decoder.raw_decode(text_variant[start:])
                obj_end += start
                prefix = text_variant[:start].strip()
                suffix = text_variant[obj_end:].strip()
                if prefix or suffix:
                    metadata['had_extra_text'] = True
                    log_info(f"[extract_json_from_text] ✅ Extracted JSON array from text with extra content (prefix: {len(prefix)} chars, suffix: {len(suffix)} chars)")
                    if prefix:
                        log_debug(f"[extract_json_from_text] Prefix text: {prefix[:100]}...")
                    if suffix:
                        log_debug(f"[extract_json_from_text] Suffix text: {suffix[:100]}...")
                    if suffix and ('{' in suffix or '"type"' in suffix or '"actions"' in suffix):
                        metadata['unparsed_content'] = suffix
                        metadata['recovered'] = True
                        log_warning(f"[extract_json_from_text] ⚠️ Corrupted JSON detected - unparsed content contains JSON-like structures")
                # Return JSON even if there's extra content - actions can still be executed
                log_debug(f"[extract_json_from_text] Found valid JSON array: {type(obj)}")
                found_json = obj
                break
            except json.JSONDecodeError as e:
                log_debug(f"[extract_json_from_text] JSON decode error at position {start}: {e}")
                metadata['had_errors'] = True
                metadata['error_count'] += 1
                continue
        
        if found_json:
            break
    
    if not found_json:
        log_debug("[extract_json_from_text] No valid JSON found in text")
        log_debug(f"[extract_json_from_text] Text content (first 500 chars): {text[:500]}")
        log_debug(f"[extract_json_from_text] Text content (last 500 chars): {text[-500:]}")
        return (None, metadata) if return_metadata else None
    
    # If we had errors but found JSON, it means we recovered from corruption
    if metadata['had_errors'] and found_json:
        metadata['recovered'] = True
        log_warning(f"[extract_json_from_text] ⚠️ JSON recovered after {metadata['error_count']} parsing errors - may be incomplete")
    
    return (found_json, metadata) if return_metadata else found_json

