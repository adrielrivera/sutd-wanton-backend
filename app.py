from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import json
import os
import threading
import time

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Timer Data Management
class Timers:
    def __init__(self, filepath):
        self.filepath = filepath
        self.timers = {}
        self.load_timers()
        self.lock = threading.Lock()  # Prevent race conditions

    def load_timers(self):
        if os.path.exists(self.filepath):
            with open(self.filepath, "r") as file:
                self.timers = json.load(file)
        else:
            self.timers = {}

    def save_timers(self):
        with open(self.filepath, "w") as file:
            json.dump(self.timers, file)

    def start_timer(self, can_id, table_id):
        duration = 900  # Default duration is 15 minutes (900 seconds)
        with self.lock:
            self.timers[can_id] = {
                "table_id": table_id,
                "remaining_time": duration,
                "alerts_sent": []  # Track sent alerts
            }
            self.save_timers()
        return duration

    def get_timer_status(self, can_id):
        with self.lock:
            return self.timers.get(can_id, None)

    def end_timer(self, can_id):
        with self.lock:
            if can_id in self.timers:
                del self.timers[can_id]
                self.save_timers()
                return True
        return False

    def decrement_timers(self):
        with self.lock:
            for can_id, timer_data in list(self.timers.items()):
                timer_data["remaining_time"] -= 1

                # Check for alerts at specific remaining times
                remaining_time = timer_data["remaining_time"]
                if remaining_time in [240, 180, 120, 60]:  # 4, 3, 2, and 1 minute alerts
                    if remaining_time not in timer_data["alerts_sent"]:
                        # Emit alert event
                        socketio.emit('timer_alert', {
                            "can_id": can_id,
                            "table_id": timer_data["table_id"],
                            "remaining_time": remaining_time
                        })
                        timer_data["alerts_sent"].append(remaining_time)

                # If timer reaches 0, emit timer ended and remove it
                if remaining_time <= 0:
                    socketio.emit('timer_ended', {"can_id": can_id, "table_id": timer_data["table_id"]})
                    del self.timers[can_id]

            self.save_timers()

timers = Timers(filepath="data/timers.json")

# Background Timer Thread
def timer_thread():
    while True:
        timers.decrement_timers()
        time.sleep(1)  # Decrement every second

threading.Thread(target=timer_thread, daemon=True).start()

# Routes
@app.route('/start_timer', methods=['POST'])
def start_timer():
    data = request.json
    can_id = data.get("can_id")
    table_id = data.get("table_id")

    if not can_id or not table_id:
        return jsonify({"error": "Missing CAN ID or Table ID"}), 400

    duration = timers.start_timer(can_id, table_id)

    # Emit event to notify clients
    socketio.emit('timer_started', {
        "can_id": can_id,
        "table_id": table_id,
        "duration": duration
    })

    return jsonify({"message": "Timer started!", "can_id": can_id, "table_id": table_id}), 200


@app.route('/get_timer_status/<can_id>', methods=['GET'])
def get_timer_status(can_id):
    timer = timers.get_timer_status(can_id)
    if not timer:
        return jsonify({"error": "Timer not found"}), 404
    return jsonify(timer)


@app.route('/end_timer/<can_id>', methods=['POST'])
def end_timer(can_id):
    success = timers.end_timer(can_id)
    if success:
        # Emit event to notify clients
        socketio.emit('timer_ended', {"can_id": can_id})
        return jsonify({"message": "Timer ended!", "can_id": can_id}), 200
    return jsonify({"error": "Timer not found"}), 404


@app.route('/admin/tables_status', methods=['GET'])
def get_tables_status():
    return jsonify(timers.timers)


@app.route('/admin/timer_duration', methods=['GET', 'POST'])
def timer_duration():
    if request.method == 'GET':
        # Return the default duration (15 minutes)
        return jsonify({"timer_duration": 900})
    elif request.method == 'POST':
        # Update the timer duration (not implemented in this version)
        return jsonify({"message": "Feature not implemented yet"}), 501


if __name__ == '__main__':
    socketio.run(app, debug=True)
