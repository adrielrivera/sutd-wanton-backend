import time
import json

class Timers:
    def __init__(self):
        self.timers = {}  # store timers in memory
        self.load_timers()  # load existing timers from file

    def save_timers(self):
        """Save timers to a JSON file."""
        with open('data/timers.json', 'w') as file:
            json.dump(self.timers, file)

    def load_timers(self):
        """Load timers from a JSON file."""
        try:
            with open('data/timers.json', 'r') as file:
                self.timers = json.load(file)
        except FileNotFoundError:
            self.timers = {}

    def start_timer(self, token_id, duration):
        """Start a new timer."""
        self.timers[token_id] = {
            "duration": duration,
            "start_time": time.time()
        }
        self.save_timers()

    def get_timer_status(self, token_id):
        """Retrieve the remaining time for a timer."""
        timer = self.timers.get(token_id)
        if not timer:
            return None
        elapsed = time.time() - timer["start_time"]
        remaining = max(0, timer["duration"] - elapsed)
        return {
            "token_id": token_id,
            "remaining_time": int(remaining)
        }

    def end_timer(self, token_id):
        """End a timer."""
        if token_id in self.timers:
            del self.timers[token_id]
            self.save_timers()
            return True
        return False
