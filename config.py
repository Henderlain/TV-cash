import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Charger depuis variables d'environnement (ou .env)
SECRET_KEY = os.environ.get("SECRET_KEY", "change_this_secret")
DATABASE = os.path.join(BASE_DIR, "data.sqlite3")

# Paiement: a renseigner avec tes credentials
ORANGE_CLIENT_ID = os.environ.get("ORANGE_CLIENT_ID", "")
ORANGE_CLIENT_SECRET = os.environ.get("ORANGE_CLIENT_SECRET", "")
ORANGE_API_BASE = os.environ.get("ORANGE_API_BASE", "https://api.orange.com")  # verifier selon doc
ORANGE_MERCHANT_ID = os.environ.get("ORANGE_MERCHANT_ID", "")

MCHAIN_API_KEY = os.environ.get("MCHAIN_API_KEY", "")
MCHAIN_API_BASE = os.environ.get("MCHAIN_API_BASE", "https://api.maschain.com")  # exemple

# Montants (en Francs CFA)
REGISTRATION_FEE = 3000
REFERRAL_BONUS = 1000
VIDEO_REWARD = 250
