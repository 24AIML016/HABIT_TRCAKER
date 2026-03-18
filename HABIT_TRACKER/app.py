from flask import Flask, flash, render_template, request, redirect, url_for, session
from models import db, User

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///userHD.db"
app.config["SECRET_KEY"] = "super-secret-key"

db.init_app(app)

with app.app_context():
    db.create_all()

# ---------------- HOME ----------------
@app.route("/")
def home():
    return render_template("index.html")

# ---------------- REGISTER ----------------
@app.route("/auth/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]
        confirm = request.form["confirm_password"]

        if password != confirm:
            return "Passwords do not match"

        if User.query.filter_by(email=email).first():
            return "User already exists"

        user = User(username=username, email=email)
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        session["user_id"] = user.id   # AUTO LOGIN
        return redirect(url_for("dashboard"))

    return render_template("auth/register.html")

# ---------------- LOGIN ----------------

from werkzeug.security import check_password_hash

@app.route('/auth/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()

        if not user:
            flash("User not found")
            return redirect(url_for('login'))

        if user.check_password(password):
            session["user_id"] = user.id
            flash("Login successful")
            return redirect(url_for('dashboard'))

        flash("Wrong password")
        return redirect(url_for('login'))

    return render_template('auth/login.html')

# ---------------- DASHBOARD ----------------

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])
    return render_template("dashboard.html", user=user)

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("home"))

if __name__ == "__main__":
    app.run(debug=True)
