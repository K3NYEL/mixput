import unittest

from app.components.core.input_protocol import (
    EVENT_TYPES,
    MAX_MESSAGE_BYTES,
    ProtocolError,
    decode_message,
    encode_input_event,
    encode_message,
)


class InputProtocolTests(unittest.TestCase):
    def test_message_round_trip(self):
        message = {"version": 1, "kind": "hello"}
        self.assertEqual(decode_message(encode_message(message).rstrip(b"\n")), message)

    def test_rejects_unsupported_input_event(self):
        with self.assertRaises(ProtocolError):
            encode_input_event({"type": "execute_command"})

    def test_rejects_oversized_message(self):
        with self.assertRaises(ProtocolError):
            encode_message({"data": "x" * (MAX_MESSAGE_BYTES + 1)})

    def test_event_allowlist_is_explicit(self):
        self.assertEqual(
            EVENT_TYPES,
            {"key_down", "key_up", "mouse_move", "mouse_button", "mouse_scroll"},
        )


if __name__ == "__main__":
    unittest.main()
