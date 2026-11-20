"""Versioned, length-limited JSON messages for Mixput input sharing."""
import json

PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 4096
EVENT_TYPES = {"key_down", "key_up", "mouse_move", "mouse_button", "mouse_scroll"}


class ProtocolError(ValueError):
    pass


def encode_message(message):
    if not isinstance(message, dict):
        raise ProtocolError("Message must be an object.")
    payload = json.dumps(message, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    if len(payload) > MAX_MESSAGE_BYTES:
        raise ProtocolError("Message exceeds the protocol size limit.")
    return payload + b"\n"


def encode_input_event(event):
    if not isinstance(event, dict) or event.get("type") not in EVENT_TYPES:
        raise ProtocolError("Unsupported input event.")
    return encode_message({"version": PROTOCOL_VERSION, "kind": "input", "event": event})


def decode_message(line):
    if not isinstance(line, bytes) or len(line) > MAX_MESSAGE_BYTES:
        raise ProtocolError("Invalid message size.")
    try:
        message = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProtocolError("Invalid message encoding.") from error
    if not isinstance(message, dict) or message.get("version") != PROTOCOL_VERSION:
        raise ProtocolError("Unsupported protocol version.")
    if message.get("kind") == "input":
        event = message.get("event")
        if not isinstance(event, dict) or event.get("type") not in EVENT_TYPES:
            raise ProtocolError("Unsupported input event.")
    return message
