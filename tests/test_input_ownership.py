import unittest

from app.components.core.input_ownership import InputOwnership


class InputOwnershipTests(unittest.TestCase):
    def test_transfer_increments_epoch_and_rejects_unknown_target(self):
        ownership = InputOwnership()
        self.assertIsNone(ownership.transfer("unknown", {"host", "client-a"}))
        self.assertEqual(ownership.snapshot(), ("host", 0))
        self.assertEqual(ownership.transfer("client-a", {"host", "client-a"}), ("host", 1))
        self.assertEqual(ownership.snapshot(), ("client-a", 1))

    def test_old_epoch_is_never_current_after_transfer(self):
        ownership = InputOwnership()
        ownership.transfer("client-a", {"host", "client-a"})
        self.assertTrue(ownership.is_current("client-a", 1))
        ownership.transfer("host", {"host", "client-a"})
        self.assertFalse(ownership.is_current("client-a", 1))
        self.assertTrue(ownership.is_current("host", 2))

    def test_force_only_increments_when_owner_changes(self):
        ownership = InputOwnership()
        self.assertEqual(ownership.force("host"), 0)
        self.assertEqual(ownership.force("client-a"), 1)
        self.assertEqual(ownership.force("client-a"), 1)


if __name__ == "__main__":
    unittest.main()
