from flask import Flask, request, jsonify, session

from flask_cors import CORS
from flask_socketio import SocketIO, emit
import json
import os
import threading
import time
from datetime import timedelta

app = Flask(__name__)
app.secret_key = "your_secret_key"  # Replace with a secure key
app.permanent_session_lifetime = timedelta(days=1)

app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_COOKIE_SECURE'] = False  # Set to False for local development
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_HTTPONLY'] = True

CORS(app, supports_credentials=True, resources={r"/*": {"origins": "http://localhost:3000"}})


socketio = SocketIO(app, cors_allowed_origins="*")

# Timer Management
class Timers:
    def __init__(self, filepath):
        self.filepath = filepath
        self.timers = {}
        self.tables = {}  # Tracks table occupancy
        self.default_duration = 900  # Default timer duration: 15 minutes
        self.load_timers()
        self.lock = threading.Lock()

    def load_timers(self):
        if os.path.exists(self.filepath):
            with open(self.filepath, "r") as file:
                data = json.load(file)
                self.timers = data.get("timers", {})
                self.tables = data.get("tables", {})
        else:
            self.timers = {}
            self.tables = {}

    def save_timers(self):
        with open(self.filepath, "w") as file:
            json.dump({"timers": self.timers, "tables": self.tables}, file)

    def start_timer(self, can_id, table_id):
        with self.lock:
            self.timers[can_id] = {
                "table_id": table_id,
                "remaining_time": self.default_duration,
                "alerts_sent": []
            }
            self.tables[table_id] = {"occupied": True, "can_id": can_id}
            self.save_timers()
        return self.default_duration

    def get_timer_status(self, can_id):
        with self.lock:
            return self.timers.get(can_id, None)

    def end_timer(self, can_id):
        with self.lock:
            if can_id in self.timers:
                table_id = self.timers[can_id]["table_id"]
                self.tables[table_id]["occupied"] = True  # Table remains occupied
                del self.timers[can_id]
                self.save_timers()
                return True
        return False

    def set_table_vacant(self, table_id):
        with self.lock:
            if table_id in self.tables and self.tables[table_id]["occupied"]:
                self.tables[table_id]["occupied"] = False
                self.tables[table_id]["can_id"] = None
                self.save_timers()
                return True
        return False

    def count_occupied_tables(self):
        with self.lock:
            return sum(1 for table in self.tables.values() if table["occupied"])

    def decrement_timers(self):
        with self.lock:
            for can_id, timer_data in list(self.timers.items()):
                timer_data["remaining_time"] -= 1
                remaining_time = timer_data["remaining_time"]
                if remaining_time in [300, 240, 180, 120, 60]:
                    if remaining_time not in timer_data["alerts_sent"]:
                        socketio.emit('timer_alert', {
                            "can_id": can_id,
                            "table_id": timer_data["table_id"],
                            "remaining_time": remaining_time
                        })
                        timer_data["alerts_sent"].append(remaining_time)
                if remaining_time <= 0:
                    socketio.emit('timer_ended', {
                        "can_id": can_id,
                        "table_id": timer_data["table_id"]
                    })
                    del self.timers[can_id]
            self.save_timers()

timers = Timers(filepath="data/timers.json")

# Background Timer Thread
def timer_thread():
    while True:
        timers.decrement_timers()
        time.sleep(1)

threading.Thread(target=timer_thread, daemon=True).start()

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    session.permanent = True

    # Check if admin login
    if data.get("is_admin", False):
        if data.get("password") == "admin":  # Hardcoded password for admin
            session['is_admin'] = True
            return jsonify({"is_admin": True, "message": "Admin login successful"}), 200
        else:
            return jsonify({"message": "Invalid admin password"}), 401

    # Regular user login
    can_id = data.get("can_id")
    if can_id:
        session['can_id'] = can_id
        session['is_admin'] = False
        return jsonify({"can_id": can_id, "is_admin": False, "message": "User login successful"}), 200
    else:
        return jsonify({"message": "CAN ID is required"}), 400





@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"message": "Logout successful"}), 200

@app.route('/user', methods=['GET'])
def get_user():
    if 'can_id' in session:
        return jsonify({
            "can_id": session['can_id'],
            "is_admin": session['is_admin']
        }), 200
    else:
        print("Session data:", dict(session))  # Debugging: print session
        return jsonify({"error": "Not logged in"}), 401

@app.route('/start_timer', methods=['POST'])
def start_timer():
    data = request.json
    can_id = data.get("can_id")
    table_id = data.get("table_id")
    if not can_id or not table_id:
        return jsonify({"error": "Missing can_id or table_id"}), 400
    duration = timers.start_timer(can_id, table_id)
    return jsonify({"message": "Timer started", "duration": duration}), 200

@app.route('/get_timer_status/<can_id>', methods=['GET'])
def get_timer_status(can_id):
    timer = timers.get_timer_status(can_id)
    if not timer:
        return jsonify({"error": "Timer not found"}), 404
    return jsonify(timer), 200

@app.route('/end_timer/<can_id>', methods=['POST'])
def end_timer(can_id):
    success = timers.end_timer(can_id)
    if success:
        return jsonify({"message": "Timer ended"}), 200
    return jsonify({"error": "Timer not found"}), 404

@app.route('/set_table_vacant', methods=['POST'])
def set_table_vacant():
    data = request.json
    table_id = data.get("table_id")
    if not table_id:
        return jsonify({"error": "Missing table_id"}), 400
    success = timers.set_table_vacant(table_id)
    if success:
        return jsonify({"message": f"Table {table_id} is now vacant"}), 200
    return jsonify({"error": "Table not found or already vacant"}), 404

@app.route('/count_occupied_tables', methods=['GET'])
def count_occupied_tables():
    if 'can_id' in session or 'is_admin' in session:
        count = timers.count_occupied_tables()
        return jsonify({"occupied_tables": count}), 200
    return jsonify({"error": "Not logged in"}), 401




@app.route('/get_timer_duration', methods=['GET'])
def get_timer_duration():
    return jsonify({"duration": timers.default_duration}), 200

@app.route('/update_timer_duration', methods=['POST'])
def update_timer_duration():
    data = request.json
    new_duration = data.get("duration")
    if not new_duration or not isinstance(new_duration, int):
        return jsonify({"error": "Invalid or missing duration"}), 400
    timers.default_duration = new_duration
    return jsonify({"message": "Timer duration updated", "new_duration": new_duration}), 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
