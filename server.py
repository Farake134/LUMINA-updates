"""
server.py — L.U.M.I.N.A Update Server
A déployer sur Render.com (gratuit)
Gère les versions et les mises à jour automatiques
"""
import os, json, hashlib
from flask import Flask, jsonify, request, send_file, abort
from datetime import datetime

app = Flask(__name__)

# ── Clé admin — CHANGEZ CECI par un mot de passe secret ──────────────────────
ADMIN_KEY = os.environ.get("ADMIN_KEY", "LUCAS_ADMIN_SECRET_2024")

# ── Fichier de version (stocké en mémoire sur Render free tier) ──────────────
# Sur Render gratuit le disque est éphémère, on utilise des variables
VERSION_DATA = {
    "version":     "1.0.0",
    "date":        "2024-01-01",
    "notes":       "Version initiale de L.U.M.I.N.A",
    "download_url": "",          # URL du .exe sur GitHub Releases
    "obligatoire":  False,       # True = force la mise à jour
}

# En production sur Render, stocker dans une variable globale
_version_store = dict(VERSION_DATA)


@app.route('/')
def home():
    return jsonify({
        "app":     "L.U.M.I.N.A Update Server",
        "status":  "online",
        "version": _version_store["version"]
    })


@app.route('/version')
def version():
    """Les clients vérifient cette route au démarrage."""
    return jsonify(_version_store)


@app.route('/check/<current_version>')
def check_update(current_version):
    """
    Retourne si une mise à jour est disponible.
    Le .exe appelle cette route avec sa version actuelle.
    """
    latest = _version_store["version"]
    needs_update = current_version != latest

    return jsonify({
        "current":      current_version,
        "latest":       latest,
        "update":       needs_update,
        "obligatoire":  _version_store.get("obligatoire", False),
        "notes":        _version_store.get("notes", ""),
        "download_url": _version_store.get("download_url", ""),
        "date":         _version_store.get("date", ""),
    })


@app.route('/publish', methods=['POST'])
def publish():
    """
    Route admin — publie une nouvelle version.
    Appelée depuis votre PC avec votre clé admin.
    """
    # Vérifier la clé admin
    key = request.headers.get("X-Admin-Key", "")
    if key != ADMIN_KEY:
        abort(403)

    data = request.json or {}
    required = ["version", "download_url"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"Champ manquant : {field}"}), 400

    _version_store.update({
        "version":      data["version"],
        "download_url": data["download_url"],
        "notes":        data.get("notes", "Nouvelle version"),
        "obligatoire":  data.get("obligatoire", False),
        "date":         datetime.now().strftime("%Y-%m-%d %H:%M"),
    })

    return jsonify({"ok": True, "version": _version_store["version"]})


@app.route('/stats', methods=['POST'])
def stats():
    """
    Les clients envoient des stats anonymes (optionnel).
    Juste pour savoir combien d'utilisateurs actifs.
    """
    # Sur Render gratuit on log juste
    data = request.json or {}
    print(f"[STAT] version={data.get('version')} os={data.get('os')}")
    return jsonify({"ok": True})


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port)
