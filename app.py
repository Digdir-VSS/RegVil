from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/run-pipeline", methods=["POST"])
def run_pipeline():
    payload = request.get_json()
    params = payload.get("params", {})

    print("Received parameters:", params)  # Prints to terminal/log

    return jsonify({
        "status": "ok",
        "received": params
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)  # Use port=5000 if you're running without Docker
