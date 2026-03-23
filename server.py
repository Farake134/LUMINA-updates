"""
server.py — L.U.M.I.N.A Backend
Données persistantes dans Firebase Firestore.
"""
import os, hashlib, secrets, string
from flask import Flask, jsonify, request, abort
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore

app = Flask(__name__)

ADMIN_KEY = os.environ.get("ADMIN_KEY", "")
GROQ_KEY  = os.environ.get("GROQ_KEY", "")

# ── FIREBASE INIT ─────────────────────────────────────────────────────────────
import json as _json

_cred_json = os.environ.get("FIREBASE_CREDENTIALS", "").strip()
try:
    if _cred_json:
        _cred_dict = _json.loads(_cred_json)
        cred = credentials.Certificate(_cred_dict)
    else:
        cred = credentials.Certificate("firebase_key.json")
    firebase_admin.initialize_app(cred)
    db = firestore.client()
except Exception as _e:
    import sys
    print("FIREBASE INIT ERROR:", _e, flush=True)
    sys.exit(1)

# ── COLLECTIONS FIRESTORE ─────────────────────────────────────────────────────
# db.collection("users")   → un document par email
# db.collection("codes")   → un document par code
# db.collection("meta")    → document "version" pour les mises à jour

# ── UTILS ─────────────────────────────────────────────────────────────────────
def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def gen_code(n=8):
    return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(n))

def is_admin(req):
    return req.headers.get("X-Admin-Key") == ADMIN_KEY and ADMIN_KEY

def get_version():
    doc = db.collection("meta").document("version").get()
    if doc.exists:
        return doc.to_dict()
    return {
        "version": "1.3.7", "download_url": "",
        "notes": "Version initiale", "obligatoire": False,
        "date": datetime.now().strftime("%Y-%m-%d")
    }


# ════════════════════════════════════════════════════════════════════════════
# ROUTES PUBLIQUES
# ════════════════════════════════════════════════════════════════════════════

@app.route('/')
def home():
    try:
        nb  = len(list(db.collection("users").stream()))
    except:
        nb  = 0
    ver = get_version()
    return jsonify({"app": "L.U.M.I.N.A Server", "status": "online",
                    "users": nb, "version": ver["version"]})


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

    # Vérifier si l'email existe déjà
    user_ref = db.collection("users").document(email)
    if user_ref.get().exists:
        return jsonify({"ok": False, "error": "Email déjà utilisé"}), 400

    # Code ou clé API
    final_key = ""
    code_used = False

    if code:
        code_ref = db.collection("codes").document(code)
        code_doc = code_ref.get()
        if not code_doc.exists:
            return jsonify({"ok": False, "error": "Code invalide"}), 400
        code_data = code_doc.to_dict()
        if code_data.get("used"):
            return jsonify({"ok": False, "error": "Code déjà utilisé"}), 400
        # Marquer le code comme utilisé
        code_ref.update({
            "used":    True,
            "used_by": email,
            "used_at": datetime.now().isoformat()
        })
        final_key = GROQ_KEY
        code_used = True
    else:
        if not api_key or not api_key.startswith("gsk_"):
            return jsonify({"ok": False, "error": "Entrez un code d'accès ou une clé API valide"}), 400
        final_key = api_key

    # Créer l'utilisateur dans Firestore
    user_ref.set({
        "username":      username,
        "password_hash": hash_pw(password),
        "api_key":       final_key,
        "created_at":    datetime.now().isoformat(),
        "code_used":     code if code_used else None,
    })
    return jsonify({"ok": True, "message": "Compte créé", "username": username})


@app.route('/login', methods=['POST'])
def login():
    data     = request.json or {}
    email    = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()

    if not email or not password:
        return jsonify({"ok": False, "error": "Email et mot de passe requis"}), 400

    doc = db.collection("users").document(email).get()
    if not doc.exists:
        return jsonify({"ok": False, "error": "Email ou mot de passe incorrect"}), 401

    user = doc.to_dict()
    if user["password_hash"] != hash_pw(password):
        return jsonify({"ok": False, "error": "Email ou mot de passe incorrect"}), 401

    return jsonify({"ok": True, "username": user["username"], "api_key": user["api_key"]})


@app.route('/check/<current_version>')
def check_update(current_version):
    ver = get_version()
    return jsonify({
        "current":      current_version,
        "latest":       ver["version"],
        "update":       current_version != ver["version"],
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
        # Générer un code unique
        c = gen_code()
        while db.collection("codes").document(c).get().exists:
            c = gen_code()
        db.collection("codes").document(c).set({
            "used":       False,
            "used_by":    None,
            "used_at":    None,
            "note":       note,
            "created_at": datetime.now().isoformat()
        })
        new.append(c)
    return jsonify({"ok": True, "codes": new, "count": len(new)})


@app.route('/admin/codes/list')
def list_codes():
    if not is_admin(request): abort(403)
    docs  = db.collection("codes").stream()
    codes = []
    for doc in docs:
        d = doc.to_dict()
        codes.append({
            "code":    doc.id,
            "used":    d.get("used", False),
            "used_by": d.get("used_by"),
            "note":    d.get("note", "")
        })
    return jsonify({"ok": True, "total": len(codes), "codes": codes})


@app.route('/admin/users/list')
def list_users():
    if not is_admin(request): abort(403)
    docs  = db.collection("users").stream()
    users = []
    for doc in docs:
        d = doc.to_dict()
        users.append({
            "email":      doc.id,
            "username":   d.get("username", ""),
            "created_at": d.get("created_at", ""),
            "code_used":  d.get("code_used")
        })
    return jsonify({"ok": True, "total": len(users), "users": users})


@app.route('/admin/users/delete', methods=['POST'])
def delete_user():
    if not is_admin(request): abort(403)
    email = (request.json or {}).get("email", "").lower()
    ref   = db.collection("users").document(email)
    if not ref.get().exists:
        return jsonify({"ok": False, "error": "Introuvable"}), 404
    ref.delete()
    return jsonify({"ok": True})


@app.route('/admin/publish', methods=['POST'])
def publish():
    if not is_admin(request): abort(403)
    data = request.json or {}
    if "version" not in data or "download_url" not in data:
        return jsonify({"error": "version et download_url requis"}), 400
    db.collection("meta").document("version").set({
        "version":      data["version"],
        "download_url": data["download_url"],
        "notes":        data.get("notes", ""),
        "obligatoire":  data.get("obligatoire", False),
        "date":         datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    return jsonify({"ok": True, "version": data["version"]})


@app.route('/admin/retirer', methods=['POST'])
def retirer():
    if not is_admin(request): abort(403)
    version = (request.json or {}).get("version", "")
    db.collection("meta").document("version").update({
        "download_url": "",
        "notes":        "",
        "obligatoire":  False,
        "version":      version
    })
    return jsonify({"ok": True})


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port)
