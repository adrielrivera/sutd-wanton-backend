from flask import Flask, request, jsonify
from flask_cors import CORS
from timers import Timers

app = Flask(__name__)
CORS(app)  # enable Cross-Origin Resource Sharing
timers = Timers()  # initialize the Timers class

@app.route('/start_timer', methods=['POST'])
def start_timer():
    data = request.json
    token_id = data.get('token_id')
    duration = data.get('duration')

    if not token_id or not duration:
        return jsonify({"error": "Missing token_id or duration"}), 400

    timers.start_timer(token_id, duration)
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

if __name__ == '__main__':
    app.run(debug=True)
