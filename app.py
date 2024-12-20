from flask import Flask, request, jsonify
from flask_cors import CORS
from timers import Timers

app = Flask(__name__)
CORS(app)  # Enable Cross-Origin Resource Sharing
timers = Timers()  # Initialize the Timers class


@app.route('/start_timer', methods=['POST'])
def start_timer():
    data = request.json
    token_id = data.get('token_id')

    if not token_id:
        return jsonify({"error": "Missing token_id"}), 400

    timers.start_timer(token_id)
    return jsonify({"message": "Timer started!", "token_id": token_id}), 200


@app.route('/get_timer_status/<token_id>', methods=['GET'])
def get_timer_status(token_id):
    timer = timers.get_timer_status(token_id)
    if not timer:
        return jsonify({"error": "Timer not found"}), 404
    return jsonify(timer)


@app.route('/end_timer/<token_id>', methods=['POST'])
def end_timer(token_id):
    success = timers.end_timer(token_id)
    if success:
        return jsonify({"message": "Timer ended"}), 200
    return jsonify({"error": "Timer not found"}), 404


@app.route('/check_in', methods=['POST'])
def check_in():
    timers.check_in()
    return jsonify({"message": "User checked in", "checked_in_users": timers.get_checked_in_users()}), 200


@app.route('/check_out', methods=['POST'])
def check_out():
    timers.check_out()
    return jsonify({"message": "User checked out", "checked_in_users": timers.get_checked_in_users()}), 200


@app.route('/admin/timer_duration', methods=['GET', 'POST'])
def timer_duration():
    if request.method == 'GET':
        return jsonify({"timer_duration": timers.get_timer_duration()}), 200
    elif request.method == 'POST':
        data = request.json
        new_duration = data.get('duration')
        if not new_duration:
            return jsonify({"error": "Missing duration"}), 400
        timers.update_timer_duration(new_duration)
        return jsonify({"message": "Timer duration updated", "timer_duration": new_duration}), 200


@app.route('/admin/checked_in_users', methods=['GET'])
def checked_in_users():
    return jsonify({"checked_in_users": timers.get_checked_in_users()}), 200


if __name__ == '__main__':
    app.run(debug=True)
