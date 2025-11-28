import os
import sqlite3
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, g, jsonify, send_from_directory
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
import numpy as np
from PIL import Image

# Try TensorFlow import
try:
    import tensorflow as tf
except Exception:
    tf = None

# Razorpay import (optional)
try:
    import razorpay
except Exception:
    razorpay = None

# -----------------------------------
# FLASK & CONFIG
# -----------------------------------
app = Flask(__name__)

app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev_secret")
DATABASE = "/tmp/database.db"
UPLOAD_FOLDER = "/tmp/uploads"
MODEL_PATH = "skin.h5"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# MAIL CONFIG
app.config.update(
    MAIL_SERVER="smtp.gmail.com",
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
)
mail = Mail(app)

# Razorpay
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

razorpay_client = None
if razorpay and RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:
    try:
        razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
    except:
        razorpay_client = None

# -----------------------------------
# DATABASE
# -----------------------------------
def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE, check_same_thread=False)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_db(e):
    db = getattr(g, "_database", None)
    if db:
        db.close()

def init_db():
    db = get_db()
    cur = db.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doctor_name TEXT,
            patient_name TEXT,
            patient_email TEXT,
            patient_phone TEXT,
            appointment_date TEXT,
            appointment_time TEXT,
            razorpay_payment_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    db.commit()

with app.app_context():
    init_db()

# -----------------------------------
# LOAD MODEL
# -----------------------------------
model = None
class_names = [
    "Actinic keratoses",
    "Basal cell carcinoma",
    "Benign keratosis-like lesions",
    "Dermatofibroma",
    "Melanocytic nevi",
    "Vascular lesions",
    "Melanoma"
]

if tf:
    try:
        model = tf.keras.models.load_model(MODEL_PATH)
    except:
        model = None

# -----------------------------------
# DISEASE INFO
# -----------------------------------
disease_info = {
    "Basal cell carcinoma": {
        "description": "Basal cell carcinoma grows slowly and rarely spreads.",
        "care": "Avoid sun exposure and consult a dermatologist."
    },
    "Actinic keratoses": {
        "description": "Rough scaly patches from sun exposure.",
        "care": "Seek early medical advice."
    },
    "Benign keratosis-like lesions": {
        "description": "Non-cancerous mole-like growths.",
        "care": "Usually harmless unless changes appear."
    },
    "Dermatofibroma": {
        "description": "Harmless skin growth due to mild skin trauma.",
        "care": "Removal only if painful."
    },
    "Melanocytic nevi": {
        "description": "Common harmless moles.",
        "care": "Monitor regularly."
    },
    "Melanoma": {
        "description": "Deadly skin cancer if untreated early.",
        "care": "Seek immediate treatment."
    },
    "Vascular lesions": {
        "description": "Irregular blood vessel growths.",
        "care": "Monitor for bleeding."
    }
}

# -----------------------------------
# AUTH ROUTES
# -----------------------------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        db = get_db()
        cur = db.cursor()

        try:
            cur.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, generate_password_hash(password))
            )
            db.commit()
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            return render_template("signup.html", error="Username already exists.")

    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT * FROM users WHERE username=?", (username,))
        user = cur.fetchone()

        if user and check_password_hash(user["password"], password):
            session["logged_in"] = True
            session["username"] = username
            return redirect(url_for("index"))

        return render_template("login.html", error="Invalid credentials.")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# -----------------------------------
# RAZORPAY ORDER
# -----------------------------------
@app.route("/create_order", methods=["POST"])
def create_order():
    if not razorpay_client:
        return jsonify({"error": "Payment gateway not configured"}), 400

    data = request.get_json()
    amount = int(data.get("amount", 99)) * 100

    order = razorpay_client.order.create({
        "amount": amount,
        "currency": "INR",
        "payment_capture": 1
    })

    return jsonify(order)

# -----------------------------------
# SAVE APPOINTMENT
# -----------------------------------
@app.route("/save_appointment", methods=["POST"])
def save_appointment():
    data = request.get_json()

    doctor = data["doctor"]
    name = data["name"]
    email = data["email"]
    phone = data["phone"]
    date = data["date"]
    time = data["time"]
    payment_id = data.get("payment_id")

    db = get_db()
    cur = db.cursor()
    cur.execute("""
        INSERT INTO appointments
        (doctor_name, patient_name, patient_email, patient_phone, appointment_date, appointment_time, razorpay_payment_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (doctor, name, email, phone, date, time, payment_id))
    db.commit()

    # SEND MAIL
    if app.config["MAIL_USERNAME"]:
        try:
            msg = Message(
                subject="Appointment Confirmation – SkinAI Hub",
                sender=app.config["MAIL_USERNAME"],
                recipients=[email],
                body=f"Hello {name},\n\nYour appointment with {doctor} on {date} at {time} is confirmed.\nPayment ID: {payment_id}\n\nThanks,\nSkinAI Hub"
            )
            mail.send(msg)
        except:
            pass

    return jsonify({"status": "success"})

# -----------------------------------
# PREDICTION + INDEX
# -----------------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    prediction_text = ""
    description = ""
    care = ""
    uploaded_file = ""

    if request.method == "POST" and model:
        file = request.files["file"]
        filename = secure_filename(file.filename)
        path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(path)

        uploaded_file = filename

        img = Image.open(path).convert("RGB")
        img = img.resize((28, 28))
        arr = np.array(img) / 255.0
        arr = np.expand_dims(arr, 0)

        pred = model.predict(arr)
        cls = class_names[int(np.argmax(pred))]
        conf = float(np.max(pred)) * 100

        prediction_text = f"{cls} ({conf:.2f}% confidence)"
        description = disease_info[cls]["description"]
        care = disease_info[cls]["care"]

    return render_template(
        "index.html",
        prediction_text=prediction_text,
        disease_description=description,
        disease_care=care,
        uploaded_image_path=uploaded_file,
        razorpay_key=RAZORPAY_KEY_ID
    )

# -----------------------------------
# SERVE UPLOADS
# -----------------------------------
@app.route("/uploads/<file>")
def uploads(file):
    return send_from_directory(UPLOAD_FOLDER, file)

# -----------------------------------
# ADMIN VIEW
# -----------------------------------
@app.route("/admin/appointments")
def admin_appt():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM appointments ORDER BY created_at DESC")
    rows = cur.fetchall()
    return render_template("appointments.html", appointments=rows)

# -----------------------------------
# RUN
# -----------------------------------
if __name__ == "__main__":
    app.run(debug=True)
