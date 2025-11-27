from flask import Flask, render_template, request, redirect, url_for, session, g, jsonify
import sqlite3
import tensorflow as tf
from PIL import Image
import numpy as np
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
import razorpay


# ----------------------------------------
# FLASK CONFIG
# ----------------------------------------
app = Flask(__name__)
app.secret_key = "skinhub123456789"
app.config['UPLOAD_FOLDER'] = 'static/uploads/'
DATABASE = "database.db"


# ----------------------------------------
# RAZORPAY PAYMENT CONFIG
# ----------------------------------------
razorpay_client = razorpay.Client(auth=(
    "RAZORPAY_KEY_ID_HERE",        # <---- replace with your Key ID
    "RAZORPAY_KEY_SECRET_HERE"     # <---- replace with your Key Secret
))


# ----------------------------------------
# EMAIL CONFIG (SMTP)
# ----------------------------------------
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True

# Replace with your Gmail + App Password
app.config['MAIL_USERNAME'] = "YOUR_EMAIL@gmail.com"
app.config['MAIL_PASSWORD'] = "YOUR_APP_PASSWORD"

mail = Mail(app)


# ----------------------------------------
# DB CONNECTION
# ----------------------------------------
def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_db(error):
    db = getattr(g, "_database", None)
    if db:
        db.close()


# ----------------------------------------
# LOAD AI MODEL
# ----------------------------------------
model = tf.keras.models.load_model("skin.h5")

class_names = [
    "Actinic keratoses",
    "Basal cell carcinoma",
    "Benign keratosis-like lesions",
    "Dermatofibroma",
    "Melanocytic nevi",
    "Vascular lesions",
    "Melanoma"
]


# ----------------------------------------
# DISEASE INFO
# ----------------------------------------
disease_info = {
    "Basal cell carcinoma": {
        "description": "Basal cell carcinoma is a common skin cancer...",
        "care": "Seek medical evaluation..."
    },
    "Actinic keratoses": {
        "description": "Rough, scaly patches...",
        "care": "Use sunscreen..."
    },
    "Benign keratosis-like lesions": {
        "description": "Non-cancerous...",
        "care": "Monitoring is enough."
    },
    "Dermatofibroma": {
        "description": "Harmless growth...",
        "care": "Remove if painful."
    },
    "Melanocytic nevi": {
        "description": "Normal moles...",
        "care": "Check for ABCDE changes."
    },
    "Melanoma": {
        "description": "Serious skin cancer...",
        "care": "Seek urgent care."
    },
    "Vascular lesions": {
        "description": "Abnormal blood vessels...",
        "care": "Monitor for bleeding."
    }
}


# ----------------------------------------
# SIGNUP
# ----------------------------------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        if not username or not password:
            return render_template("signup.html", error="All fields required")

        db = get_db()
        cur = db.cursor()
        hashed_pw = generate_password_hash(password)

        try:
            cur.execute("INSERT INTO users (username, password) VALUES (?, ?)",
                        (username, hashed_pw))
            db.commit()
        except sqlite3.IntegrityError:
            return render_template("signup.html", error="Username already exists")

        return redirect(url_for("login"))

    return render_template("signup.html")


# ----------------------------------------
# LOGIN
# ----------------------------------------
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

        return render_template("login.html", error="Invalid username or password")

    return render_template("login.html")


# ----------------------------------------
# LOGOUT
# ----------------------------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ----------------------------------------
# RAZORPAY: CREATE ORDER (BEFORE APPOINTMENT)
# ----------------------------------------
@app.route("/create_order", methods=["POST"])
def create_order():

    data = request.get_json()
    amount = int(data.get("amount", 99)) * 100  # ₹99 default

    order = razorpay_client.order.create({
        "amount": amount,
        "currency": "INR",
        "payment_capture": 1
    })

    return jsonify(order)


# ----------------------------------------
# SAVE APPOINTMENT + EMAIL CONFIRMATION
# ----------------------------------------
@app.route("/save_appointment", methods=["POST"])
def save_appointment():

    if not session.get("logged_in"):
        return {"status": "error", "message": "Unauthorized"}, 401

    try:
        data = request.get_json()
        print("Received JSON:", data)

        doctor = data["doctor"]
        name = data["name"]
        email = data["email"]
        phone = data["phone"]
        date = data["date"]
        time = data["time"]

        db = get_db()
        cur = db.cursor()

        cur.execute("""
            INSERT INTO appointments 
            (doctor_name, patient_name, patient_email, patient_phone, appointment_date, appointment_time)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (doctor, name, email, phone, date, time))

        db.commit()

        # Send confirmation mail
        msg = Message(
            subject="Your Appointment Confirmation – SkinAI Hub",
            sender=app.config['MAIL_USERNAME'],
            recipients=[email]
        )

        msg.body = f"""
Hello {name},

Your appointment has been booked successfully!

Doctor: {doctor}
Date: {date}
Time: {time}

Thank you for using SkinAI Hub!
"""
        mail.send(msg)

        return {"status": "success"}

    except Exception as e:
        print("ERROR:", e)
        return {"status": "error", "message": str(e)}


# ----------------------------------------
# MAIN INDEX (AI PREDICTION)
# ----------------------------------------
@app.route("/", methods=["GET", "POST"])
def index():

    if not session.get("logged_in"):
        return redirect(url_for("login"))

    prediction_text = ""
    uploaded_image_path = ""
    disease_description = ""
    disease_care = ""

    if request.method == "POST":

        if "file" not in request.files:
            return "No file found"

        file = request.files["file"]

        if file.filename == "":
            return "No file selected"

        filename = secure_filename(file.filename)
        uploaded_image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(uploaded_image_path)

        img = Image.open(uploaded_image_path).convert('RGB')
        img = img.resize((28, 28))
        img_array = np.array(img) / 255.0
        img_array = np.expand_dims(img_array, 0)

        prediction = model.predict(img_array)
        pred_class = np.argmax(prediction)
        label = class_names[pred_class]
        confidence = np.max(prediction)

        info = disease_info.get(label, {})
        disease_description = info.get("description", "No info available")
        disease_care = info.get("care", "No care info")

        prediction_text = f"{label} ({confidence * 100:.2f}% confidence)"

    return render_template(
        "index.html",
        prediction_text=prediction_text,
        uploaded_image_path=uploaded_image_path,
        disease_description=disease_description,
        disease_care=disease_care,
        username=session.get("username")
    )


# ----------------------------------------
# RUN APP
# ----------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
