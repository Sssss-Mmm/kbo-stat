"""One atomic rolling budget shared by stories and question answering."""
import os
from collections import deque
from threading import Lock
from time import monotonic


class AIBudget:
    def __init__(self):
        self.calls = deque()
        self.lock = Lock()

    def take(self, count: int = 1) -> bool:
        with self.lock:
            now = monotonic()
            while self.calls and self.calls[0] <= now - 86400:
                self.calls.popleft()
            limit = max(0, int(os.getenv("AI_MAX_CALLS_PER_DAY", "20")))
            if len(self.calls) + count > limit:
                return False
            self.calls.extend([now] * count)
            return True

    def refund(self, count: int) -> None:
        # Returns reserved calls that were never made.
        with self.lock:
            for _ in range(min(count, len(self.calls))):
                self.calls.pop()


ai_budget = AIBudget()
