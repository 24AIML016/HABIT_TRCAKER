from flask import Flask, flash, render_template, request, redirect, url_for, session, jsonify
from models import db, User, Habit, HabitCompletion
from datetime import date, timedelta
from functools import wraps
from collections import defaultdict
import os
import calendar

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///habitu.db"
app.config["SECRET_KEY"] = os.urandom(24).hex()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

with app.app_context():
    db.create_all()


# ── Login-required decorator ──────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def get_current_user():
    return db.session.get(User, session.get("user_id"))


# ── HOME ──────────────────────────────────────────────────────
@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("index.html")


# ── REGISTER ──────────────────────────────────────────────────
@app.route("/auth/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not username or not email or not password:
            flash("All fields are required.", "error")
            return redirect(url_for("register"))

        if password != confirm:
            flash("Passwords do not match.", "error")
            return redirect(url_for("register"))

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return redirect(url_for("register"))

        if User.query.filter_by(email=email).first():
            flash("An account with this email already exists.", "error")
            return redirect(url_for("register"))

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        session["user_id"] = user.id
        flash(f"Welcome to Habitu, {username}! 🎉", "success")
        return redirect(url_for("dashboard"))

    return render_template("auth/register.html")


# ── LOGIN ─────────────────────────────────────────────────────
@app.route("/auth/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            flash("Invalid email or password.", "error")
            return redirect(url_for("login"))

        session["user_id"] = user.id
        flash(f"Welcome back, {user.username}!", "success")
        return redirect(url_for("dashboard"))

    return render_template("auth/login.html")


# ── DASHBOARD ─────────────────────────────────────────────────
@app.route("/dashboard")
@login_required
def dashboard():
    user = get_current_user()
    habits = Habit.query.filter_by(user_id=user.id).order_by(Habit.created_at.desc()).all()

    total_habits = len(habits)
    completed_today = sum(1 for h in habits if h.completed_today)
    completion_pct = int((completed_today / total_habits * 100)) if total_habits > 0 else 0
    best_streak = max((h.streak for h in habits), default=0)

    # Weekly data for chart (last 7 days)
    weekly_data = []
    today = date.today()
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        count = sum(
            1 for h in habits
            if any(c.completed_date == d for c in h.completions)
        )
        weekly_data.append({
            "day": d.strftime("%a"),
            "date": d.isoformat(),
            "count": count
        })

    return render_template(
        "dashboard.html",
        user=user,
        habits=habits,
        total_habits=total_habits,
        completed_today=completed_today,
        completion_pct=completion_pct,
        best_streak=best_streak,
        weekly_data=weekly_data,
        today=today
    )


# ── ADD HABIT ─────────────────────────────────────────────────
@app.route("/habit/add", methods=["POST"])
@login_required
def add_habit():
    name = request.form.get("name", "").strip()
    icon = request.form.get("icon", "✨")
    color = request.form.get("color", "#6c5ce7")
    habit_type = request.form.get("habit_type", "boolean")
    target_value = request.form.get("target_value", 0, type=float)
    unit = request.form.get("unit", "").strip()

    if not name:
        flash("Habit name is required.", "error")
        return redirect(url_for("dashboard"))

    if habit_type == "countable" and target_value <= 0:
        flash("Target value must be greater than 0.", "error")
        return redirect(url_for("dashboard"))

    habit = Habit(
        user_id=session["user_id"],
        name=name,
        icon=icon,
        color=color,
        habit_type=habit_type,
        target_value=target_value,
        unit=unit
    )
    db.session.add(habit)
    db.session.commit()

    flash(f'Habit "{name}" created! 🚀', "success")
    return redirect(url_for("dashboard"))


# ── TOGGLE HABIT COMPLETION ───────────────────────────────────
@app.route("/habit/<int:habit_id>/toggle", methods=["POST"])
@login_required
def toggle_habit(habit_id):
    habit = Habit.query.get_or_404(habit_id)
    if habit.user_id != session["user_id"]:
        flash("Unauthorized.", "error")
        return redirect(url_for("dashboard"))

    today = date.today()
    existing = HabitCompletion.query.filter_by(
        habit_id=habit_id, completed_date=today
    ).first()

    if habit.habit_type == "countable":
        # For countable habits, accept a value from the form
        value = request.form.get("value", 0, type=float)
        if existing:
            existing.value = value
            db.session.commit()
        else:
            completion = HabitCompletion(habit_id=habit_id, completed_date=today, value=value)
            db.session.add(completion)
            db.session.commit()

        if value >= habit.target_value:
            flash(f'🎉 Target reached! "{habit.name}" — {value} {habit.unit}!', "success")
        else:
            flash(f'Logged {value} {habit.unit} for "{habit.name}".', "info")
    else:
        # Boolean toggle
        if existing:
            db.session.delete(existing)
            db.session.commit()
            flash(f'Unmarked "{habit.name}" for today.', "info")
        else:
            completion = HabitCompletion(habit_id=habit_id, completed_date=today)
            db.session.add(completion)
            db.session.commit()
            flash(f'Great job! "{habit.name}" completed! 🔥', "success")

    return redirect(url_for("dashboard"))


# ── DELETE HABIT ──────────────────────────────────────────────
@app.route("/habit/<int:habit_id>/delete", methods=["POST"])
@login_required
def delete_habit(habit_id):
    habit = Habit.query.get_or_404(habit_id)
    if habit.user_id != session["user_id"]:
        flash("Unauthorized.", "error")
        return redirect(url_for("dashboard"))

    name = habit.name
    db.session.delete(habit)
    db.session.commit()
    flash(f'Habit "{name}" deleted.', "info")
    return redirect(url_for("dashboard"))


# ── STATISTICS PAGE ───────────────────────────────────────────
@app.route("/statistics")
@login_required
def statistics():
    user = get_current_user()
    habits = Habit.query.filter_by(user_id=user.id).order_by(Habit.created_at.desc()).all()
    return render_template("statistics.html", user=user, habits=habits)


# ── STATISTICS API ────────────────────────────────────────────
@app.route("/api/stats")
@login_required
def api_stats():
    user = get_current_user()
    habits = Habit.query.filter_by(user_id=user.id).all()
    today = date.today()

    # 1. Weekly completions (last 7 days)
    weekly_labels = []
    weekly_counts = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        count = sum(
            1 for h in habits
            if any(c.completed_date == d for c in h.completions)
        )
        weekly_labels.append(d.strftime("%a"))
        weekly_counts.append(count)

    # 2. Monthly completions (last 30 days)
    monthly_labels = []
    monthly_counts = []
    for i in range(29, -1, -1):
        d = today - timedelta(days=i)
        count = sum(
            1 for h in habits
            if any(c.completed_date == d for c in h.completions)
        )
        monthly_labels.append(d.strftime("%d %b"))
        monthly_counts.append(count)

    # 3. Per-habit completion rate (all time)
    habit_names = []
    habit_rates = []
    habit_colors = []
    habit_streaks = []
    for h in habits:
        habit_names.append(f"{h.icon} {h.name}")
        habit_colors.append(h.color)
        habit_streaks.append(h.streak)
        days_since = max(1, (today - h.created_at.date()).days + 1)
        rate = min(100, int(h.total_completions / days_since * 100))
        habit_rates.append(rate)

    # 4. Completion heatmap (last 12 weeks = 84 days)
    heatmap = []
    for i in range(83, -1, -1):
        d = today - timedelta(days=i)
        count = sum(
            1 for h in habits
            if any(c.completed_date == d for c in h.completions)
        )
        total = len(habits) if len(habits) > 0 else 1
        heatmap.append({
            "date": d.isoformat(),
            "day": d.strftime("%a"),
            "label": d.strftime("%b %d"),
            "count": count,
            "total": total,
            "pct": int(count / total * 100)
        })

    # 5. Overall summary
    total_completions = sum(h.total_completions for h in habits)
    total_habits = len(habits)
    completed_today = sum(1 for h in habits if h.completed_today)
    best_streak = max((h.streak for h in habits), default=0)
    avg_daily = 0
    if total_habits > 0:
        last_30_completions = sum(
            1 for h in habits
            for c in h.completions
            if (today - c.completed_date).days < 30
        )
        avg_daily = round(last_30_completions / 30, 1)

    # 6. Day-of-week averages
    dow_counts = defaultdict(list)
    for i in range(27, -1, -1):
        d = today - timedelta(days=i)
        count = sum(
            1 for h in habits
            if any(c.completed_date == d for c in h.completions)
        )
        dow_counts[d.strftime("%a")].append(count)

    dow_order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    dow_avgs = [
        round(sum(dow_counts.get(d, [0])) / max(len(dow_counts.get(d, [1])), 1), 1)
        for d in dow_order
    ]

    return jsonify({
        "weekly": {"labels": weekly_labels, "data": weekly_counts},
        "monthly": {"labels": monthly_labels, "data": monthly_counts},
        "habits": {
            "names": habit_names,
            "rates": habit_rates,
            "colors": habit_colors,
            "streaks": habit_streaks
        },
        "heatmap": heatmap,
        "summary": {
            "total_habits": total_habits,
            "completed_today": completed_today,
            "total_completions": total_completions,
            "best_streak": best_streak,
            "avg_daily": avg_daily
        },
        "dow": {"labels": dow_order, "data": dow_avgs}
    })


# ── LOGOUT ────────────────────────────────────────────────────
@app.route("/logout")
def logout():
    session.clear()
    flash("You've been logged out.", "info")
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(debug=True)
