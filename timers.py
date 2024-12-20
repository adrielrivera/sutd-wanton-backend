import time
import json

class Timers:
    def __init__(self):
        self.timers = {}  # Tracks active timers
        self.timer_duration = 300  # Default timer duration
        self.load_timers()

    def save_timers(self):
        """Save timers to a JSON file."""
        with open('data/timers.json', 'w') as file:
            json.dump(self.timers, file)

    def load_timers(self):
        """Load timers from a JSON file."""
        try:
            with open('data/timers.json', 'r') as file:
                self.timers = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            self.timers = {}

    def start_timer(self, can_id, table_id):
        """Start a timer for a CAN ID and associate it with a table."""
        self.timers[can_id] = {
            "duration": self.timer_duration,
            "start_time": time.time(),
            "table_id": table_id
        }
        self.save_timers()

    def get_timer_status(self, can_id):
        """Retrieve the remaining time and table ID for a CAN ID."""
        timer = self.timers.get(can_id)
        if not timer:
            return None
        elapsed = time.time() - timer["start_time"]
        remaining = max(0, timer["duration"] - elapsed)
        return {
            "can_id": can_id,
            "remaining_time": int(remaining),
            "table_id": timer["table_id"]
        }

    def end_timer(self, can_id):
        """End a timer for a CAN ID and free the associated table."""
        if can_id in self.timers:
            del self.timers[can_id]
            self.save_timers()
            return True
        return False

    def update_timer_duration(self, new_duration):
        """Update the default timer duration."""
        self.timer_duration = new_duration
        self.save_timers()

    def get_all_timers(self):
        """Return the status of all active timers."""
        return self.timers
