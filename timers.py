import time
import json

class Timers:
    def __init__(self):
        self.timers = {}  # Track active timers
        self.checked_in_users = 0  # Track number of users checked in
        self.timer_duration = 300  # Default timer duration
        self.load_timers()

    def save_timers(self):
        """Save timers and metadata to a JSON file."""
        data = {
            "timers": self.timers,
            "checked_in_users": self.checked_in_users,
            "timer_duration": self.timer_duration
        }
        with open('data/timers.json', 'w') as file:
            json.dump(data, file)

    def load_timers(self):
        """Load timers and metadata from a JSON file."""
        try:
            with open('data/timers.json', 'r') as file:
                data = json.load(file)
                self.timers = data.get("timers", {})
                self.checked_in_users = data.get("checked_in_users", 0)
                self.timer_duration = data.get("timer_duration", 300)
        except (FileNotFoundError, json.JSONDecodeError):
            self.timers = {}
            self.checked_in_users = 0
            self.timer_duration = 300

    def start_timer(self, token_id):
        """Start a timer for a token."""
        self.timers[token_id] = {
            "duration": self.timer_duration,
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

    def check_in(self):
        """Increment the number of users checked in."""
        self.checked_in_users += 1
        self.save_timers()

    def check_out(self):
        """Decrement the number of users checked in."""
        if self.checked_in_users > 0:
            self.checked_in_users -= 1
            self.save_timers()

    def get_checked_in_users(self):
        """Return the number of checked-in users."""
        return self.checked_in_users

    def update_timer_duration(self, new_duration):
        """Update the timer duration."""
        self.timer_duration = new_duration
        self.save_timers()

    def get_timer_duration(self):
        """Get the current timer duration."""
        return self.timer_duration
