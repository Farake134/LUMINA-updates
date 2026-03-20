"""
server.py — L.U.M.I.N.A Update Server
"""
import os, json
from flask import Flask, jsonify, request, abort
from datetime import datetime

app = Flask(__name__)

ADMIN_KEY = os.environ.get("ADMIN_KEY", "Lucas2024Secret!")

_store = {
    "version":      "1.0.0",
    "date":         "2026-03-20",
    "notes":        "Version initiale",
    "download_url": "",
    "obligatoire":  False,
}

@app.route('/')
def home():
    return jsonify({"app": "L.U.M.I.N.A Update Server", "status": "online", "version": _store["version"]})

@app.route('/version')
def version():
    return jsonify(_store)

@app.route('/check/<current_version>')
def check(current_version):
    latest = _store["version"]
    return jsonify({
        "current":      current_version,
        "latest":       latest,
        "update":       current_version != latest,
        "obligatoire":  _store["obligatoire"],
        "notes":        _store["notes"],
        "download_url": _store["download_url"],
        "date":         _store["date"],
    })

@app.route('/publish', methods=['POST'])
def publish():
    if request.headers.get("X-Admin-Key") != ADMIN_KEY:
        abort(403)
    data = request.json or {}
    if "version" not in data or "download_url" not in data:
        return jsonify({"error": "version et download_url requis"}), 400
    _store.update({
        "version":      data["version"],
        "download_url": data["download_url"],
        "notes":        data.get("notes", ""),
        "obligatoire":  data.get("obligatoire", False),
        "date":         datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    return jsonify({"ok": True, "version": _store["version"]})

@app.route('/retirer', methods=['POST'])
def retirer():
    if request.headers.get("X-Admin-Key") != ADMIN_KEY:
        abort(403)
    # Remettre la version actuelle = version du .exe = pas de mise à jour
    data = request.json or {}
    _store["version"]      = data.get("version", _store["version"])
    _store["download_url"] = ""
    _store["notes"]        = ""
    _store["obligatoire"]  = False
    return jsonify({"ok": True, "message": f'Mise à jour retirée. Version actuelle : {_store["version"]}' })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port)
