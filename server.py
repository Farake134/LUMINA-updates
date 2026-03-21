"""
server.py — L.U.M.I.N.A Backend
Gère : comptes utilisateurs, codes d'accès, mises à jour
"""
import os, json, hashlib, secrets, string
from flask import Flask, jsonify, request, abort
from datetime import datetime

app = Flask(__name__)

# ── CLÉS ──────────────────────────────────────────────────────────────────────
ADMIN_KEY = os.environ.get("ADMIN_KEY", "2024Secret!")
GROQ_KEY  = os.environ.get("GROQ_KEY", "")   # Votre clé Groq pour les codes gratuits

# ── STOCKAGE EN MÉMOIRE ───────────────────────────────────────────────────────
# Sur Render gratuit le disque est éphémère — on stocke en mémoire
# Les données sont perdues si le serveur redémarre (upgrade pour persistance)
_users   = {}   # {email: {password_hash, username, created_at, api_key}}
_codes   = {}   # {code: {used, used_by, created_at, note}}
_version = {
    "version":      "1.3.0",
    "download_url": "",
    "notes":        "Version initiale",
    "obligatoire":  False,
    "date":         "2026-03-20",
}


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generate_code(length=8):
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))

def check_admin(req):
    return req.headers.get("X-Admin-Key") == ADMIN_KEY


# ════════════════════════════════════════════════════════════════════════════
# ROUTES PUBLIQUES
# ════════════════════════════════════════════════════════════════════════════

@app.route('/')
def home():
    return jsonify({
        "app":     "L.U.M.I.N.A Server",
        "status":  "online",
        "users":   len(_users),
        "version": _version["version"]
    })


@app.route('/register', methods=['POST'])
def register():
    """Créer un compte avec email + mot de passe + code optionnel."""
    data     = request.json or {}
    email    = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    username = data.get("username", "").strip()
    code     = data.get("code", "").strip().upper()

    # Validation
    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "Email invalide"}), 400
    if len(password) < 6:
        return jsonify({"ok": False, "error": "Mot de passe trop court (6 min)"}), 400
    if not username:
        return jsonify({"ok": False, "error": "Nom requis"}), 400
    if email in _users:
        return jsonify({"ok": False, "error": "Email déjà utilisé"}), 400

    # Déterminer la clé API à utiliser
    api_key = ""
    code_used = False

    if code:
        if code not in _codes:
            return jsonify({"ok": False, "error": "Code invalide"}), 400
        if _codes[code]["used"]:
            return jsonify({"ok": False, "error": "Code déjà utilisé"}), 400
        # Code valide → utiliser la clé Groq du serveur
        api_key = GROQ_KEY
        _codes[code]["used"]    = True
        _codes[code]["used_by"] = email
        _codes[code]["used_at"] = datetime.now().isoformat()
        code_used = True
    else:
        # Pas de code → l'utilisateur doit fournir sa propre clé
        api_key = data.get("api_key", "").strip()
        if not api_key or not api_key.startswith("gsk_"):
            return jsonify({"ok": False, "error": "Clé API requise sans code"}), 400

    _users[email] = {
        "username":      username,
        "password_hash": hash_password(password),
        "api_key":       api_key,
        "created_at":    datetime.now().isoformat(),
        "code_used":     code if code_used else None,
    }

    return jsonify({
        "ok":      True,
        "message": "Compte créé avec succès",
        "username": username,
    })


@app.route('/login', methods=['POST'])
def login():
    """Connexion avec email + mot de passe."""
    data     = request.json or {}
    email    = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()

    if not email or not password:
        return jsonify({"ok": False, "error": "Email et mot de passe requis"}), 400

    user = _users.get(email)
    if not user:
        return jsonify({"ok": False, "error": "Email ou mot de passe incorrect"}), 401
    if user["password_hash"] != hash_password(password):
        return jsonify({"ok": False, "error": "Email ou mot de passe incorrect"}), 401

    return jsonify({
        "ok":       True,
        "username": user["username"],
        "api_key":  user["api_key"],
    })


@app.route('/check/<current_version>')
def check_update(current_version):
    latest = _version["version"]
    return jsonify({
        "current":      current_version,
        "latest":       latest,
        "update":       current_version != latest,
        "obligatoire":  _version["obligatoire"],
        "notes":        _version["notes"],
        "download_url": _version["download_url"],
        "date":         _version["date"],
    })


# ════════════════════════════════════════════════════════════════════════════
# ROUTES ADMIN
# ════════════════════════════════════════════════════════════════════════════

@app.route('/admin/codes/create', methods=['POST'])
def create_code():
    """Générer un ou plusieurs codes d'accès."""
    if not check_admin(request): abort(403)
    data  = request.json or {}
    count = data.get("count", 1)
    note  = data.get("note", "")

    new_codes = []
    for _ in range(min(count, 50)):
        code = generate_code()
        while code in _codes:
            code = generate_code()
        _codes[code] = {
            "used":       False,
            "used_by":    None,
            "used_at":    None,
            "note":       note,
            "created_at": datetime.now().isoformat(),
        }
        new_codes.append(code)

    return jsonify({"ok": True, "codes": new_codes, "count": len(new_codes)})


@app.route('/admin/codes/list')
def list_codes():
    """Lister tous les codes."""
    if not check_admin(request): abort(403)
    result = []
    for code, data in _codes.items():
        result.append({
            "code":       code,
            "used":       data["used"],
            "used_by":    data["used_by"],
            "note":       data["note"],
            "created_at": data["created_at"],
        })
    return jsonify({"ok": True, "codes": result, "total": len(result)})


@app.route('/admin/users/list')
def list_users():
    """Lister tous les utilisateurs."""
    if not check_admin(request): abort(403)
    result = []
    for email, data in _users.items():
        result.append({
            "email":      email,
            "username":   data["username"],
            "created_at": data["created_at"],
            "code_used":  data["code_used"],
        })
    return jsonify({"ok": True, "users": result, "total": len(result)})


@app.route('/admin/users/delete', methods=['POST'])
def delete_user():
    """Supprimer un utilisateur."""
    if not check_admin(request): abort(403)
    email = (request.json or {}).get("email", "").lower()
    if email in _users:
        del _users[email]
        return jsonify({"ok": True, "message": "Utilisateur supprimé"})
    return jsonify({"ok": False, "error": "Utilisateur introuvable"}), 404


@app.route('/admin/publish', methods=['POST'])
def publish():
    """Publier une nouvelle version."""
    if not check_admin(request): abort(403)
    data = request.json or {}
    if "version" not in data or "download_url" not in data:
        return jsonify({"error": "version et download_url requis"}), 400
    _version.update({
        "version":      data["version"],
        "download_url": data["download_url"],
        "notes":        data.get("notes", ""),
        "obligatoire":  data.get("obligatoire", False),
        "date":         datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    return jsonify({"ok": True, "version": _version["version"]})


@app.route('/admin/retirer', methods=['POST'])
def retirer():
    """Retirer une mise à jour."""
    if not check_admin(request): abort(403)
    version = (request.json or {}).get("version", _version["version"])
    _version.update({"version": version, "download_url": "", "notes": "", "obligatoire": False})
    return jsonify({"ok": True, "message": "Mise à jour retirée"})


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port)
