from flask import Flask, request, jsonify
from flask_cors import CORS
from timers import Timers

app = Flask(__name__)
CORS(app)  # Enable Cross-Origin Resource Sharing
timers = Timers()  # Initialize the Timers class


@app.route('/start_timer', methods=['POST'])
def start_timer():
    """Start a timer for a CAN ID and associate it with a table."""
    data = request.json
    can_id = data.get('can_id')
    table_id = data.get('table_id')

    if not can_id or not table_id:
        return jsonify({"error": "Missing can_id or table_id"}), 400

    timers.start_timer(can_id, table_id)
    return jsonify({
        "message": "Timer started",
        "table_id": table_id,
        "can_id": can_id,
        "duration": timers.timer_duration
    }), 200


@app.route('/get_timer_status/<can_id>', methods=['GET'])
def get_timer_status(can_id):
    """Get the remaining time and table ID for a CAN ID."""
    timer = timers.get_timer_status(can_id)
    if not timer:
        return jsonify({"error": "Timer not found"}), 404
    return jsonify(timer)


@app.route('/end_timer/<can_id>', methods=['POST'])
def end_timer(can_id):
    """End a timer for a CAN ID."""
    success = timers.end_timer(can_id)
    if success:
        return jsonify({"message": "Timer ended"}), 200
    return jsonify({"error": "Timer not found"}), 404


@app.route('/admin/timer_duration', methods=['GET', 'POST'])
def timer_duration():
    """View or update the default timer duration."""
    if request.method == 'GET':
        return jsonify({"timer_duration": timers.timer_duration}), 200
    elif request.method == 'POST':
        data = request.json
        new_duration = data.get('duration')
        if not new_duration:
            return jsonify({"error": "Missing duration"}), 400
        timers.update_timer_duration(new_duration)
        return jsonify({"message": "Timer duration updated", "timer_duration": new_duration}), 200


@app.route('/admin/tables_status', methods=['GET'])
def tables_status():
    """Get the status of all active timers (tables)."""
    return jsonify(timers.get_all_timers()), 200


if __name__ == '__main__':
    app.run(debug=True)
