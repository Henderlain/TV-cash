from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify # type: ignore
from werkzeug.security import generate_password_hash, check_password_hash # type: ignore
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin # type: ignore
import sqlite3
import os
import uuid
import requests # type: ignore
from config import * # type: ignore

# --- APP & Login ---
app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY # type: ignore

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# --- DATABASE HELPERS ---
def get_db():
    conn = sqlite3.connect(DATABASE) # type: ignore
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        password TEXT,
        phone TEXT,
        balance INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 0,
        referral_code TEXT UNIQUE,
        referred_by TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        provider TEXT, -- 'youtube' or 'tiktok'
        embed_url TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS views (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        video_id INTEGER,
        rewarded INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        provider TEXT,
        amount INTEGER,
        status TEXT,
        external_id TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.commit()
    conn.close()

if not os.path.exists(DATABASE): # type: ignore
    init_db()

# --- USER MODEL FOR FLASK-LOGIN ---
class User(UserMixin):
    def __init__(self, row):
        self.id = row['id']
        self.email = row['email']
        self.password_hash = row['password']
        self.phone = row['phone']
        self.balance = row['balance']
        self.is_active = bool(row['is_active'])
        self.referral_code = row['referral_code']
        self.referred_by = row['referred_by']

@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return User(row)
    return None

# --- HELPERS ---
def generate_referral_code():
    return str(uuid.uuid4())[:8]

def find_user_by_email(email):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (email,))
    row = cur.fetchone()
    conn.close()
    return row

def find_user_by_refcode(code):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE referral_code = ?", (code,))
    row = cur.fetchone()
    conn.close()
    return row

# --- ROUTES ---
@app.route("/")
def index():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM videos ORDER BY id DESC")
    videos = cur.fetchall()
    conn.close()
    return render_template("index.html", videos=videos)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        phone = request.form["phone"].strip()
        ref = request.form.get("referral", "").strip()

        if find_user_by_email(email):
            flash("Email déjà enregistré.", "warning")
            return redirect(url_for("register"))

        pw_hash = generate_password_hash(password)
        refcode = generate_referral_code()

        conn = get_db(); cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (email,password,phone,referral_code,referred_by)
            VALUES (?,?,?,?,?)
        """, (email, pw_hash, phone, refcode, ref or None))
        user_id = cur.lastrowid
        conn.commit()
        conn.close()

        # créer une payment pending pour l'inscription
        # On redirige vers checkout (simulate / initiate payment)
        return redirect(url_for("checkout", user_id=user_id))
    return render_template("register.html", reg_fee=REGISTRATION_FEE) # type: ignore

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        row = find_user_by_email(email)
        if row and check_password_hash(row["password"], password):
            user = User(row)
            login_user(user)
            flash("Connecté avec succès", "success")
            return redirect(url_for("dashboard"))
        flash("Identifiants invalides", "danger")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Déconnecté", "info")
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM videos ORDER BY id DESC")
    videos = cur.fetchall()
    # récupérer statistiques utilisateur
    cur.execute("SELECT COUNT(*) as refs FROM users WHERE referred_by = ?", (current_user.referral_code,))
    refs = cur.fetchone()["refs"]
    conn.close()
    return render_template("dashboard.html", videos=videos, refs=refs, user=current_user, reg_fee=REGISTRATION_FEE) # type: ignore

# --- CHECKOUT / INITIATE PAYMENT ---
@app.route("/checkout/<int:user_id>", methods=["GET"])
def checkout(user_id):
    # page qui démarre le paiement pour les frais d'inscription
    # on propose plusieurs moyens (Orange, M-Chain) ; ici on génère une "payment" en status pending
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cur.fetchone()
    if not user:
        flash("Utilisateur introuvable", "danger")
        return redirect(url_for("index"))

    # créer entrée paiement pending
    cur.execute("""
        INSERT INTO payments (user_id, provider, amount, status)
        VALUES (?, ?, ?, ?)
    """, (user_id, "pending", REGISTRATION_FEE, "pending")) # type: ignore
    payment_id = cur.lastrowid
    conn.commit()
    conn.close()

    # Afficher page choisissant fournisseur
    return render_template("checkout.html", user=user, payment_id=payment_id, reg_fee=REGISTRATION_FEE) # type: ignore

# Exemple d'appel pour démarrer un paiement via Orange (pseudo-code)
@app.route("/pay/orange/<int:payment_id>", methods=["POST"])
def pay_orange(payment_id):
    # Récupérer payment, user
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM payments WHERE id = ?", (payment_id,))
    payment = cur.fetchone()
    cur.execute("SELECT * FROM users WHERE id = ?", (payment["user_id"],))
    user = cur.fetchone()

    if not payment or not user:
        return "Paiement non trouvé", 404

    # === Ici : appel réel à l'API Orange pour initier la transaction ===
    # Exemple (acquérir token, puis créer transaction). Nous fournissons un placeholder.
    # Tu devras remplacer par la logique d'auth / création de paiement selon la doc Orange.
    #
    # Ex (pseudo) :
    # token = obtain_orange_token()
    # resp = requests.post(ORANGE_API_BASE + "/payment/v1/transactions", headers=..., json={...})
    #
    # Pour démo on stocke external_id simulé
    external_id = "ORANGE_SIM_"+str(uuid.uuid4())[:12]
    cur.execute("UPDATE payments SET provider = ?, external_id = ? WHERE id = ?", ("orange", external_id, payment_id))
    conn.commit()
    conn.close()

    # En production tu redirigeras vers la page de confirmation d'Orange ou géreras callback/webhook
    flash("Paiement initié via Orange (simulation). Utilise webhook / confirmation pour finaliser.", "info")
    return redirect(url_for("index"))

# Exemple d'appel pour démarrer un paiement via M-Chain (pseudo-code)
@app.route("/pay/mchain/<int:payment_id>", methods=["POST"])
def pay_mchain(payment_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM payments WHERE id = ?", (payment_id,))
    payment = cur.fetchone()
    cur.execute("SELECT * FROM users WHERE id = ?", (payment["user_id"],))
    user = cur.fetchone()
    if not payment or not user:
        return "Paiement non trouvé", 404

    external_id = "MCHAIN_SIM_"+str(uuid.uuid4())[:12]
    cur.execute("UPDATE payments SET provider = ?, external_id = ? WHERE id = ?", ("mchain", external_id, payment_id))
    conn.commit()
    conn.close()

    flash("Paiement initié via M-Chain (simulation). Utilise webhook / confirmation pour finaliser.", "info")
    return redirect(url_for("index"))

# --- WEBHOOK / PAYMENT CONFIRMATION (à exposer publiquement, utilisé par Orange/M-Chain) ---
# Pour tests on fournit une route admin qui simule la confirmation
@app.route("/webhook/simulate_payment/<int:payment_id>", methods=["POST"])
def simulate_payment(payment_id):
    # Simuler callback provider confirmant paiement réussi
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM payments WHERE id = ?", (payment_id,))
    payment = cur.fetchone()
    if not payment:
        return jsonify({"error":"not found"}), 404

    # Set status to 'paid'
    cur.execute("UPDATE payments SET status = ? WHERE id = ?", ("paid", payment_id))
    # activer utilisateur
    cur.execute("UPDATE users SET is_active = 1 WHERE id = ?", (payment["user_id"],))
    # appliquer bonus de parrainage si applicable
    cur.execute("SELECT referred_by FROM users WHERE id = ?", (payment["user_id"],))
    row = cur.fetchone()
    if row and row["referred_by"]:
        # trouver le parrain
        cur.execute("SELECT * FROM users WHERE referral_code = ?", (row["referred_by"],))
        parrain = cur.fetchone()
        if parrain:
            # créditer le parrain de REFERRAL_BONUS
            new_balance = parrain["balance"] + REFERRAL_BONUS # type: ignore
            cur.execute("UPDATE users SET balance = ? WHERE id = ?", (new_balance, parrain["id"]))
    conn.commit()
    conn.close()
    return jsonify({"status":"ok","payment_id": payment_id})

# --- VIDEO / REWARD FLOW ---
@app.route("/video/<int:video_id>")
@login_required
def video_detail(video_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM videos WHERE id = ?", (video_id,))
    video = cur.fetchone()
    conn.close()
    if not video:
        flash("Vidéo introuvable", "danger")
        return redirect(url_for("dashboard"))
    return render_template("video_detail.html", video=video)

@app.route("/video/claim/<int:video_id>", methods=["POST"])
@login_required
def claim_video_reward(video_id):
    # vérifier que l'utilisateur n'a pas déjà été récompensé pour cette vidéo
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM views WHERE user_id = ? AND video_id = ?", (current_user.id, video_id))
    row = cur.fetchone()
    if row and row["rewarded"] == 1:
        return jsonify({"status":"already_rewarded"}), 400

    # Créer enregistrement view et créditer
    cur.execute("INSERT INTO views (user_id, video_id, rewarded) VALUES (?,?,1)", (current_user.id, video_id))
    # créditer solde
    cur.execute("SELECT balance FROM users WHERE id = ?", (current_user.id,))
    u = cur.fetchone()
    new_balance = (u["balance"] or 0) + VIDEO_REWARD # type: ignore
    cur.execute("UPDATE users SET balance = ? WHERE id = ?", (new_balance, current_user.id))
    conn.commit()
    conn.close()
    return jsonify({"status":"ok","new_balance": new_balance})

# --- ADMIN SIMPLE: ajouter vidéo (pour tests) ---
@app.route("/admin/add_video", methods=["POST"])
def admin_add_video():
    # NOTE: en prod ajouter auth
    title = request.form.get("title")
    provider = request.form.get("provider")  # youtube or tiktok
    embed_url = request.form.get("embed_url")  # url pour iframe src
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT INTO videos (title, provider, embed_url) VALUES (?,?,?)", (title, provider, embed_url))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

# --- LANCER APP ---
if __name__ == "__main__":
    app.run(debug=True)
