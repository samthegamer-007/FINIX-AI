"""Flask entrypoint. One Render web service: /api/* is the JSON/SSE API, everything
else serves the built React app (frontend/dist) with SPA fallback, so routes such as
/auth, /chat/<id>, /portfolio, /admin and /admin-dashboard all load the same index.html.
Admin and user authorisation is enforced server-side on the API, not in the browser."""
import os

from flask import Flask, jsonify, send_from_directory

import auth
import routes

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.abspath(os.path.join(HERE, "..", "frontend", "dist"))

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024      # hard cap above the 5 MB upload limit
app.register_blueprint(auth.bp)
app.register_blueprint(routes.bp)


@app.get("/healthz")
def healthz():                      # UptimeRobot pings this
    return jsonify(status="ok")


@app.errorhandler(413)
def too_big(_):
    return jsonify(error="File too large."), 413


@app.errorhandler(404)
def not_found(_):
    from flask import request
    if request.path.startswith("/api/"):
        return jsonify(error="not found"), 404
    return spa(request.path.lstrip("/"))


@app.get("/", defaults={"path": ""})
@app.get("/<path:path>")
def spa(path):
    if path == "api" or path.startswith("api/"):
        return jsonify(error="not found"), 404
    if not os.path.isdir(DIST):
        return ("FINIX API is running. Frontend build not found (frontend/dist).", 200)
    candidate = os.path.join(DIST, path)
    if path and os.path.isfile(candidate):
        return send_from_directory(DIST, path)
    return send_from_directory(DIST, "index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False, threaded=True)
