import unittest

from app.components.core.input_protocol import (
    PROTOCOL_VERSION,
    ProtocolError,
    decode_message,
    encode_input_event,
    encode_message,
)


class InputProtocolTests(unittest.TestCase):
    def test_valid_input_event_round_trip(self):
        event = {"type": "mouse_move", "dx": 4, "dy": -2}
        encoded = encode_input_event(event)
        self.assertEqual(
            decode_message(encoded.rstrip(b"\\n")),
            {"version": PROTOCOL_VERSION, "kind": "input", "event": event},
        )

    def test_rejects_unknown_input_event(self):
        with self.assertRaises(ProtocolError):
            encode_input_event({"type": "execute_command"})

    def test_rejects_oversized_message(self):
        with self.assertRaises(ProtocolError):
            encode_message({"kind": "chat", "text": "x" * 5000})


if __name__ == "__main__":
    unittest.main()
