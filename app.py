
import os
import sqlite3
from pathlib import Path
from functools import wraps
from flask_wtf.csrf import CSRFProtect

from flask import (
    Flask, render_template, request,
    redirect, url_for, session, flash, g
)
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "placementpro.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "local-development-key-change-before-deployment"
)

csrf = CSRFProtect(app)

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            company TEXT NOT NULL,
            role TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Applied',
            applied_date TEXT NOT NULL DEFAULT (DATE('now')),
            notes TEXT DEFAULT '',
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    
    db.execute("""
        CREATE TABLE IF NOT EXISTS interviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            company TEXT NOT NULL,
            role TEXT NOT NULL,
            interview_round TEXT NOT NULL,
            interview_date TEXT NOT NULL,
            interview_time TEXT NOT NULL,
            mode TEXT NOT NULL DEFAULT 'Online',
            status TEXT NOT NULL DEFAULT 'Scheduled',
            notes TEXT DEFAULT '',
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)

    
    db.execute("""
        CREATE TABLE IF NOT EXISTS preparation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            topic TEXT NOT NULL,
            category TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Not Started',
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)


    db.commit()
    db.close()


def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if "user_id" not in session:
            flash("Please log in first.")
            return redirect(url_for("login"))
        return view(**kwargs)
    return wrapped_view


@app.route("/")
@login_required
def dashboard():
    db = get_db()
    user_id = session["user_id"]

    application_count = db.execute(
        "SELECT COUNT(*) FROM applications WHERE user_id = ?",
        (user_id,)
    ).fetchone()[0]

    interview_count = db.execute(
        """
        SELECT COUNT(*) FROM interviews
        WHERE user_id = ? AND status = 'Scheduled'
        """,
        (user_id,)
    ).fetchone()[0]

    offer_count = db.execute(
        """
        SELECT COUNT(*) FROM applications
        WHERE user_id = ? AND status = 'Offer'
        """,
        (user_id,)
    ).fetchone()[0]

    
    preparation_count = db.execute(
        """
        SELECT COUNT(*)
        FROM preparation
        WHERE user_id = ?
        """,
        (user_id,)
    ).fetchone()[0]

    completed_count = db.execute(
        """
        SELECT COUNT(*)
        FROM preparation
        WHERE user_id = ? AND status = 'Completed'
        """,
        (user_id,)
    ).fetchone()[0]

    in_progress_count = db.execute(
        """
        SELECT COUNT(*)
        FROM preparation
        WHERE user_id = ? AND status = 'In Progress'
        """,
        (user_id,)
    ).fetchone()[0]

    preparation_percentage = (
        round(completed_count / preparation_count * 100)
        if preparation_count > 0 else 0
    )


    upcoming_interviews = db.execute(
        """
        SELECT company, role, interview_round,
               interview_date, interview_time, mode
        FROM interviews
        WHERE user_id = ?
          AND status = 'Scheduled'
          AND (interview_date || ' ' || interview_time) >= datetime('now', 'localtime')
        ORDER BY interview_date ASC, interview_time ASC
        LIMIT 5
        """,
        (user_id,)
    ).fetchall()

    
    category_progress = db.execute(
        """
        SELECT category,
               COUNT(*) AS total,
               SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END)
                   AS completed
        FROM preparation
        WHERE user_id = ?
        GROUP BY category
        ORDER BY category
        """,
        (user_id,)
    ).fetchall()


    return render_template (
        "dashboard.html",
        name=session["name"],
        application_count=application_count,
        interview_count=interview_count,
        offer_count=offer_count,
        upcoming_interviews=upcoming_interviews,
        preparation_count=preparation_count,
        completed_count=completed_count,
        in_progress_count=in_progress_count,
        preparation_percentage=preparation_percentage,
        category_progress=category_progress,
    )



@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or len(password) < 10:
            flash("Enter your name, email and a password of at least 10 characters.")
            return render_template("register.html"), 400

        db = get_db()
        try:
            db.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, generate_password_hash(password))
            )
            db.commit()
        except sqlite3.IntegrityError:
            flash("That email is already registered. Please log in.")
            return render_template("register.html"), 409

        flash("Account created! You can now log in.")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = get_db().execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.")

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    flash("You have logged out.")
    return redirect(url_for("login"))


@app.route("/applications")
@login_required
def applications():
    db = get_db()
    records = db.execute(
        """
        SELECT id, company, role, status, applied_date, notes
        FROM applications
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (session["user_id"],)
    ).fetchall()

    return render_template("applications.html", applications=records)


@app.route("/applications/add", methods=["POST"])
@login_required
def add_application():
    company = request.form.get("company", "").strip()
    role = request.form.get("role", "").strip()
    status = request.form.get("status", "Applied").strip()
    notes = request.form.get("notes", "").strip()

    allowed_statuses = {
        "Applied", "Assessment", "Interview", "Offer", "Rejected"
    }

    if not company or not role or status not in allowed_statuses:
        flash("Enter a company and role, and select a valid status.")
        return redirect(url_for("applications"))

    db = get_db()
    db.execute(
        """
        INSERT INTO applications (user_id, company, role, status, notes)
        VALUES (?, ?, ?, ?, ?)
        """,
        (session["user_id"], company, role, status, notes)
    )
    db.commit()

    flash("Application added successfully!")
    return redirect(url_for("applications"))


@app.route("/applications/<int:application_id>/edit", methods=["GET", "POST"])
@login_required
def edit_application(application_id):
    db = get_db()

    application = db.execute(
        """
        SELECT * FROM applications
        WHERE id = ? AND user_id = ?
        """,
        (application_id, session["user_id"])
    ).fetchone()

    if application is None:
        flash("Application not found.")
        return redirect(url_for("applications"))

    if request.method == "POST":
        company = request.form.get("company", "").strip()
        role = request.form.get("role", "").strip()
        status = request.form.get("status", "").strip()
        notes = request.form.get("notes", "").strip()

        allowed_statuses = {
            "Applied", "Assessment", "Interview", "Offer", "Rejected"
        }

        if (
            not company
            or not role
            or len(company) > 150
            or len(role) > 150
            or len(notes) > 2000
            or status not in allowed_statuses
        ):
            flash("Check the company, role, status and notes.")
            return render_template(
                "edit_application.html", application=application
            ), 400

        db.execute(
            """
            UPDATE applications
            SET company = ?, role = ?, status = ?, notes = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                company, role, status, notes,
                application_id, session["user_id"]
            )
        )
        db.commit()

        flash("Application updated successfully!")
        return redirect(url_for("applications"))

    return render_template(
        "edit_application.html", application=application
    )


@app.route("/applications/<int:application_id>/delete", methods=["POST"])
@login_required
def delete_application(application_id):
    db = get_db()

    result = db.execute(
        """
        DELETE FROM applications
        WHERE id = ? AND user_id = ?
        """,
        (application_id, session["user_id"])
    )
    db.commit()

    if result.rowcount:
        flash("Application deleted successfully.")
    else:
        flash("Application not found.")

    return redirect(url_for("applications"))


@app.route("/interviews")
@login_required
def interviews():
    db = get_db()

    records = db.execute(
        """
        SELECT id, company, role, interview_round,
               interview_date, interview_time, mode, status, notes
        FROM interviews
        WHERE user_id = ?
        ORDER BY interview_date ASC, interview_time ASC
        """,
        (session["user_id"],)
    ).fetchall()

    return render_template("interviews.html", interviews=records)


@app.route("/interviews/add", methods=["POST"])
@login_required
def add_interview():
    company = request.form.get("company", "").strip()
    role = request.form.get("role", "").strip()
    interview_round = request.form.get("interview_round", "").strip()
    interview_date = request.form.get("interview_date", "").strip()
    interview_time = request.form.get("interview_time", "").strip()
    mode = request.form.get("mode", "Online").strip()
    status = request.form.get("status", "Scheduled").strip()
    notes = request.form.get("notes", "").strip()

    allowed_modes = {"Online", "In-person", "Phone"}
    allowed_statuses = {"Scheduled", "Completed", "Cancelled"}

    if (
        not company or len(company) > 150
        or not role or len(role) > 150
        or not interview_round or len(interview_round) > 100
        or not interview_date or not interview_time
        or mode not in allowed_modes
        or status not in allowed_statuses
        or len(notes) > 2000
    ):
        flash("Please check the interview details and try again.")
        return redirect(url_for("interviews"))

    db = get_db()
    db.execute(
        """
        INSERT INTO interviews (
            user_id, company, role, interview_round,
            interview_date, interview_time, mode, status, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session["user_id"], company, role, interview_round,
            interview_date, interview_time, mode, status, notes
        )
    )
    db.commit()

    flash("Interview scheduled successfully!")
    return redirect(url_for("interviews"))


@app.route("/interviews/<int:interview_id>/edit", methods=["GET", "POST"])
@login_required
def edit_interview(interview_id):
    db = get_db()

    interview = db.execute(
        """
        SELECT * FROM interviews
        WHERE id = ? AND user_id = ?
        """,
        (interview_id, session["user_id"])
    ).fetchone()

    if interview is None:
        flash("Interview not found.")
        return redirect(url_for("interviews"))

    if request.method == "POST":
        company = request.form.get("company", "").strip()
        role = request.form.get("role", "").strip()
        interview_round = request.form.get("interview_round", "").strip()
        interview_date = request.form.get("interview_date", "").strip()
        interview_time = request.form.get("interview_time", "").strip()
        mode = request.form.get("mode", "").strip()
        status = request.form.get("status", "").strip()
        notes = request.form.get("notes", "").strip()

        allowed_modes = {"Online", "In-person", "Phone"}
        allowed_statuses = {"Scheduled", "Completed", "Cancelled"}

        if (
            not company or len(company) > 150
            or not role or len(role) > 150
            or not interview_round or len(interview_round) > 100
            or not interview_date or not interview_time
            or mode not in allowed_modes
            or status not in allowed_statuses
            or len(notes) > 2000
        ):
            flash("Please check the interview details and try again.")
            return redirect(
                url_for("edit_interview", interview_id=interview_id)
            )

        db.execute(
            """
            UPDATE interviews
            SET company = ?, role = ?, interview_round = ?,
                interview_date = ?, interview_time = ?, mode = ?,
                status = ?, notes = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                company, role, interview_round, interview_date,
                interview_time, mode, status, notes,
                interview_id, session["user_id"]
            )
        )
        db.commit()

        flash("Interview updated successfully!")
        return redirect(url_for("interviews"))

    return render_template("edit_interview.html", interview=interview)


@app.route("/interviews/<int:interview_id>/delete", methods=["POST"])
@login_required
def delete_interview(interview_id):
    db = get_db()

    result = db.execute(
        """
        DELETE FROM interviews
        WHERE id = ? AND user_id = ?
        """,
        (interview_id, session["user_id"])
    )
    db.commit()

    if result.rowcount:
        flash("Interview deleted successfully.")
    else:
        flash("Interview not found.")

    return redirect(url_for("interviews"))


@app.route("/preparation", methods=["GET", "POST"])
@login_required
def preparation():
    db = get_db()
    user_id = session["user_id"]

    if request.method == "POST":
        topic = request.form.get("topic", "").strip()
        category = request.form.get("category", "").strip()
        status = request.form.get("status", "Not Started").strip()
        notes = request.form.get("notes", "").strip()

        allowed_categories = [
            "Aptitude",
            "Coding",
            "Technical",
            "HR Interview"
        ]

        allowed_statuses = [
            "Not Started",
            "In Progress",
            "Completed"
        ]

        if not topic:
            flash("Please enter a preparation topic.")
        elif category not in allowed_categories:
            flash("Please select a valid category.")
        elif status not in allowed_statuses:
            flash("Please select a valid status.")
        else:
            db.execute(
                """
                INSERT INTO preparation
                    (user_id, topic, category, status, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, topic, category, status, notes)
            )
            db.commit()
            flash("Preparation topic added successfully!")
            return redirect(url_for("preparation"))

    topics = db.execute(
        """
        SELECT id, topic, category, status, notes, created_at
        FROM preparation
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (user_id,)
    ).fetchall()

    return render_template("preparation.html", topics=topics)


@app.route("/preparation/edit/<int:topic_id>", methods=["GET", "POST"])
@login_required
def edit_preparation(topic_id):
    db = get_db()
    user_id = session["user_id"]

    topic = db.execute(
        "SELECT * FROM preparation WHERE id = ? AND user_id = ?",
        (topic_id, user_id)
    ).fetchone()

    if topic is None:
        flash("Preparation topic not found.")
        return redirect(url_for("preparation"))

    if request.method == "POST":
        name = request.form.get("topic", "").strip()
        category = request.form.get("category", "").strip()
        status = request.form.get("status", "").strip()
        notes = request.form.get("notes", "").strip()

        allowed_categories = [
            "Aptitude", "Coding", "Technical", "HR Interview"
        ]
        allowed_statuses = [
            "Not Started", "In Progress", "Completed"
        ]

        if not name:
            flash("Topic name is required.")
        elif category not in allowed_categories:
            flash("Please select a valid category.")
        elif status not in allowed_statuses:
            flash("Please select a valid status.")
        else:
            db.execute(
                """
                UPDATE preparation
                SET topic = ?, category = ?, status = ?, notes = ?
                WHERE id = ? AND user_id = ?
                """,
                (name, category, status, notes, topic_id, user_id)
            )
            db.commit()
            flash("Preparation topic updated successfully!")
            return redirect(url_for("preparation"))

    return render_template("edit_preparation.html", topic=topic)


@app.route("/preparation/delete/<int:topic_id>", methods=["POST"])
@login_required
def delete_preparation(topic_id):
    db = get_db()
    user_id = session["user_id"]

    db.execute(
        "DELETE FROM preparation WHERE id = ? AND user_id = ?",
        (topic_id, user_id)
    )
    db.commit()

    flash("Preparation topic deleted.")
    return redirect(url_for("preparation"))




if __name__ == "__main__":
    init_db()
    app.run(debug=True)