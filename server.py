"""
server.py — L.U.M.I.N.A Backend
Sauvegarde persistante dans des fichiers JSON.
"""
import os, json, hashlib, secrets, string
from flask import Flask, jsonify, request, abort
from datetime import datetime

app = Flask(__name__)

ADMIN_KEY = os.environ.get("ADMIN_KEY", "")
GROQ_KEY  = os.environ.get("GROQ_KEY", "")

# ── CHEMINS FICHIERS ──────────────────────────────────────────────────────────
DATA_DIR   = "/tmp/lumina_data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
CODES_FILE = os.path.join(DATA_DIR, "codes.json")
VER_FILE   = os.path.join(DATA_DIR, "version.json")

os.makedirs(DATA_DIR, exist_ok=True)

# ── CHARGEMENT / SAUVEGARDE ───────────────────────────────────────────────────
def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_users():   return load_json(USERS_FILE, {})
def get_codes():   return load_json(CODES_FILE, {})
def get_version(): return load_json(VER_FILE, {
    "version": "1.3.7", "download_url": "",
    "notes": "Version initiale", "obligatoire": False,
    "date": "2026-03-22"
})

def save_users(d):   save_json(USERS_FILE, d)
def save_codes(d):   save_json(CODES_FILE, d)
def save_version(d): save_json(VER_FILE, d)

# ── UTILS ─────────────────────────────────────────────────────────────────────
def hash_pw(pw):   return hashlib.sha256(pw.encode()).hexdigest()
def gen_code(n=8): return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(n))
def is_admin(req): return req.headers.get("X-Admin-Key") == ADMIN_KEY and ADMIN_KEY


# ════════════════════════════════════════════════════════════════════════════
# ROUTES PUBLIQUES
# ════════════════════════════════════════════════════════════════════════════

@app.route('/')
def home():
    users = get_users()
    ver   = get_version()
    return jsonify({"app": "L.U.M.I.N.A Server", "status": "online",
                    "users": len(users), "version": ver["version"]})


@app.route('/register', methods=['POST'])
def register():
    data     = request.json or {}
    email    = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    username = data.get("username", "").strip()
    code     = data.get("code", "").strip().upper()
    api_key  = data.get("api_key", "").strip()

    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "Email invalide"}), 400
    if len(password) < 6:
        return jsonify({"ok": False, "error": "Mot de passe trop court (6 min)"}), 400
    if not username:
        return jsonify({"ok": False, "error": "Nom requis"}), 400

    users = get_users()
    if email in users:
        return jsonify({"ok": False, "error": "Email déjà utilisé"}), 400

    # Code ou clé API
    final_key  = ""
    code_used  = False
    codes      = get_codes()

    if code:
        if code not in codes:
            return jsonify({"ok": False, "error": "Code invalide"}), 400
        if codes[code]["used"]:
            return jsonify({"ok": False, "error": "Code déjà utilisé"}), 400
        final_key = GROQ_KEY
        codes[code]["used"]    = True
        codes[code]["used_by"] = email
        codes[code]["used_at"] = datetime.now().isoformat()
        save_codes(codes)
        code_used = True
    else:
        if not api_key or not api_key.startswith("gsk_"):
            return jsonify({"ok": False, "error": "Entrez un code d'accès ou une clé API valide"}), 400
        final_key = api_key

    users[email] = {
        "username":      username,
        "password_hash": hash_pw(password),
        "api_key":       final_key,
        "created_at":    datetime.now().isoformat(),
        "code_used":     code if code_used else None,
    }
    save_users(users)
    return jsonify({"ok": True, "message": "Compte créé", "username": username})


@app.route('/login', methods=['POST'])
def login():
    data     = request.json or {}
    email    = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()

    if not email or not password:
        return jsonify({"ok": False, "error": "Email et mot de passe requis"}), 400

    users = get_users()
    user  = users.get(email)
    if not user or user["password_hash"] != hash_pw(password):
        return jsonify({"ok": False, "error": "Email ou mot de passe incorrect"}), 401

    return jsonify({"ok": True, "username": user["username"], "api_key": user["api_key"]})


@app.route('/check/<current_version>')
def check_update(current_version):
    ver = get_version()
    return jsonify({
        "current":      current_version,
        "latest":       ver["version"],
        "update":       current_version != ver["version"],
        "obligatoire":  ver["obligatoire"],
        "notes":        ver["notes"],
        "download_url": ver["download_url"],
        "date":         ver["date"],
    })


# ════════════════════════════════════════════════════════════════════════════
# ROUTES ADMIN
# ════════════════════════════════════════════════════════════════════════════

@app.route('/admin/codes/create', methods=['POST'])
def create_code():
    if not is_admin(request): abort(403)
    data  = request.json or {}
    count = min(data.get("count", 1), 50)
    note  = data.get("note", "")
    codes = get_codes()
    new   = []
    for _ in range(count):
        c = gen_code()
        while c in codes: c = gen_code()
        codes[c] = {"used": False, "used_by": None, "used_at": None,
                    "note": note, "created_at": datetime.now().isoformat()}
        new.append(c)
    save_codes(codes)
    return jsonify({"ok": True, "codes": new, "count": len(new)})


@app.route('/admin/codes/list')
def list_codes():
    if not is_admin(request): abort(403)
    codes = get_codes()
    return jsonify({"ok": True, "total": len(codes),
                    "codes": [{"code": c, "used": d["used"],
                               "used_by": d["used_by"], "note": d["note"]}
                              for c, d in codes.items()]})


@app.route('/admin/users/list')
def list_users():
    if not is_admin(request): abort(403)
    users = get_users()
    return jsonify({"ok": True, "total": len(users),
                    "users": [{"email": e, "username": d["username"],
                               "created_at": d["created_at"],
                               "code_used": d["code_used"]}
                              for e, d in users.items()]})


@app.route('/admin/users/delete', methods=['POST'])
def delete_user():
    if not is_admin(request): abort(403)
    email = (request.json or {}).get("email", "").lower()
    users = get_users()
    if email in users:
        del users[email]
        save_users(users)
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Introuvable"}), 404


@app.route('/admin/publish', methods=['POST'])
def publish():
    if not is_admin(request): abort(403)
    data = request.json or {}
    if "version" not in data or "download_url" not in data:
        return jsonify({"error": "version et download_url requis"}), 400
    ver = get_version()
    ver.update({"version": data["version"], "download_url": data["download_url"],
                "notes": data.get("notes", ""), "obligatoire": data.get("obligatoire", False),
                "date": datetime.now().strftime("%Y-%m-%d %H:%M")})
    save_version(ver)
    return jsonify({"ok": True, "version": ver["version"]})


@app.route('/admin/retirer', methods=['POST'])
def retirer():
    if not is_admin(request): abort(403)
    ver = get_version()
    ver.update({"download_url": "", "notes": "", "obligatoire": False})
    ver["version"] = (request.json or {}).get("version", ver["version"])
    save_version(ver)
    return jsonify({"ok": True})


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port)
