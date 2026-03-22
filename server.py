"""
server.py — L.U.M.I.N.A Backend
Base de données Supabase — données permanentes
"""
import os, json, hashlib, secrets, string, requests as req
from flask import Flask, jsonify, request, abort
from datetime import datetime

app = Flask(__name__)

ADMIN_KEY    = os.environ.get("ADMIN_KEY", "")
GROQ_KEY     = os.environ.get("GROQ_KEY", "")
SUPA_URL     = os.environ.get("SUPA_URL", "")
SUPA_KEY     = os.environ.get("SUPA_KEY", "")

def supa_headers():
    return {
        "apikey":        SUPA_KEY,
        "Authorization": "Bearer " + SUPA_KEY,
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
    }

def supa_get(table, params=""):
    r = req.get(SUPA_URL + "/rest/v1/" + table + params,
                headers=supa_headers(), timeout=10)
    return r.json() if r.status_code < 300 else []

def supa_post(table, data):
    r = req.post(SUPA_URL + "/rest/v1/" + table,
                 headers=supa_headers(), json=data, timeout=10)
    return r.status_code < 300

def supa_patch(table, match, data):
    r = req.patch(SUPA_URL + "/rest/v1/" + table + "?" + match,
                  headers=supa_headers(), json=data, timeout=10)
    return r.status_code < 300

def supa_delete(table, match):
    r = req.delete(SUPA_URL + "/rest/v1/" + table + "?" + match,
                   headers=supa_headers(), timeout=10)
    return r.status_code < 300

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def gen_code(n=8):
    return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(n))

def is_admin(r):
    return r.headers.get("X-Admin-Key") == ADMIN_KEY and ADMIN_KEY

def get_version():
    rows = supa_get("version", "?id=eq.1")
    if rows and isinstance(rows, list) and len(rows) > 0:
        return rows[0]
    return {"version": "1.3.7", "download_url": "", "notes": "", "obligatoire": False, "date": ""}


# ════════════════════════════════════════════════════════════════════════════
# ROUTES PUBLIQUES
# ════════════════════════════════════════════════════════════════════════════

@app.route('/')
def home():
    users = supa_get("users", "?select=email")
    ver   = get_version()
    return jsonify({"app": "L.U.M.I.N.A Server", "status": "online",
                    "users": len(users) if isinstance(users, list) else 0,
                    "version": ver.get("version", "1.3.7")})


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

    # Vérifier si email existe déjà
    existing = supa_get("users", "?email=eq." + email)
    if isinstance(existing, list) and len(existing) > 0:
        return jsonify({"ok": False, "error": "Email déjà utilisé"}), 400

    final_key = ""
    code_used = False

    if code:
        rows = supa_get("codes", "?code=eq." + code)
        if not isinstance(rows, list) or len(rows) == 0:
            return jsonify({"ok": False, "error": "Code invalide"}), 400
        if rows[0]["used"]:
            return jsonify({"ok": False, "error": "Code déjà utilisé"}), 400
        final_key = GROQ_KEY
        supa_patch("codes", "code=eq." + code, {
            "used": True, "used_by": email,
            "used_at": datetime.now().isoformat()
        })
        code_used = True
    else:
        if not api_key or not api_key.startswith("gsk_"):
            return jsonify({"ok": False, "error": "Entrez un code d'accès ou une clé API valide"}), 400
        final_key = api_key

    ok = supa_post("users", {
        "email":         email,
        "username":      username,
        "password_hash": hash_pw(password),
        "api_key":       final_key,
        "code_used":     code if code_used else None,
    })

    if not ok:
        return jsonify({"ok": False, "error": "Erreur serveur"}), 500

    return jsonify({"ok": True, "message": "Compte créé", "username": username})


@app.route('/login', methods=['POST'])
def login():
    data     = request.json or {}
    email    = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()

    if not email or not password:
        return jsonify({"ok": False, "error": "Email et mot de passe requis"}), 400

    rows = supa_get("users", "?email=eq." + email)
    if not isinstance(rows, list) or len(rows) == 0:
        return jsonify({"ok": False, "error": "Email ou mot de passe incorrect"}), 401
    user = rows[0]
    if user["password_hash"] != hash_pw(password):
        return jsonify({"ok": False, "error": "Email ou mot de passe incorrect"}), 401

    return jsonify({"ok": True, "username": user["username"], "api_key": user["api_key"]})


@app.route('/check/<current_version>')
def check_update(current_version):
    ver = get_version()
    return jsonify({
        "current":      current_version,
        "latest":       ver.get("version", "1.3.7"),
        "update":       current_version != ver.get("version", "1.3.7"),
        "obligatoire":  ver.get("obligatoire", False),
        "notes":        ver.get("notes", ""),
        "download_url": ver.get("download_url", ""),
        "date":         ver.get("date", ""),
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
    new   = []
    for _ in range(count):
        c = gen_code()
        supa_post("codes", {"code": c, "used": False, "note": note,
                            "created_at": datetime.now().isoformat()})
        new.append(c)
    return jsonify({"ok": True, "codes": new, "count": len(new)})


@app.route('/admin/codes/list')
def list_codes():
    if not is_admin(request): abort(403)
    codes = supa_get("codes", "?order=created_at.desc")
    if not isinstance(codes, list): codes = []
    return jsonify({"ok": True, "total": len(codes),
                    "codes": [{"code": c["code"], "used": c["used"],
                               "used_by": c.get("used_by"), "note": c.get("note","")}
                              for c in codes]})


@app.route('/admin/users/list')
def list_users():
    if not is_admin(request): abort(403)
    users = supa_get("users", "?order=created_at.desc")
    if not isinstance(users, list): users = []
    return jsonify({"ok": True, "total": len(users),
                    "users": [{"email": u["email"], "username": u["username"],
                               "created_at": u.get("created_at",""),
                               "code_used": u.get("code_used")}
                              for u in users]})


@app.route('/admin/users/delete', methods=['POST'])
def delete_user():
    if not is_admin(request): abort(403)
    email = (request.json or {}).get("email", "").lower()
    ok = supa_delete("users", "email=eq." + email)
    return jsonify({"ok": ok})


@app.route('/admin/publish', methods=['POST'])
def publish():
    if not is_admin(request): abort(403)
    data = request.json or {}
    if "version" not in data or "download_url" not in data:
        return jsonify({"error": "version et download_url requis"}), 400
    supa_patch("version", "id=eq.1", {
        "version":      data["version"],
        "download_url": data["download_url"],
        "notes":        data.get("notes", ""),
        "obligatoire":  data.get("obligatoire", False),
        "date":         datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    return jsonify({"ok": True, "version": data["version"]})


@app.route('/admin/retirer', methods=['POST'])
def retirer():
    if not is_admin(request): abort(403)
    version = (request.json or {}).get("version", "")
    supa_patch("version", "id=eq.1", {
        "download_url": "", "notes": "", "obligatoire": False,
        "version": version
    })
    return jsonify({"ok": True})


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port)
