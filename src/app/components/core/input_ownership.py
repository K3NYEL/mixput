"""Authoritative, versioned ownership state for shared input routing."""
import threading


class InputOwnership:
    """Serialize ownership transfers and version every successful transition."""

    def __init__(self, initial_owner="host"):
        if not isinstance(initial_owner, str) or not initial_owner:
            raise ValueError("An initial input owner is required.")
        self._owner = initial_owner
        self._epoch = 0
        self._lock = threading.RLock()

    @property
    def owner(self):
        with self._lock:
            return self._owner

    @property
    def epoch(self):
        with self._lock:
            return self._epoch

    def snapshot(self):
        with self._lock:
            return self._owner, self._epoch

    def transfer(self, target, allowed_targets):
        if not isinstance(target, str) or not target:
            return None
        with self._lock:
            if target not in allowed_targets or target == self._owner:
                return None
            previous = self._owner
            self._owner = target
            self._epoch += 1
            return previous, self._epoch

    def force(self, target):
        if not isinstance(target, str) or not target:
            raise ValueError("A valid input owner is required.")
        with self._lock:
            if target != self._owner:
                self._owner = target
                self._epoch += 1
            return self._epoch

    def is_current(self, owner, epoch):
        with self._lock:
            return owner == self._owner and epoch == self._epoch
