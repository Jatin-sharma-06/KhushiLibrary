"""Flask entry point for the beginner-friendly library website."""
import os
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash

import database as db

BASE_DIR = Path(__file__).resolve().parent
BOOKS_DIR = BASE_DIR / "books"
MAX_UPLOAD = 10 * 1024 * 1024


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(SECRET_KEY=os.environ.get("SECRET_KEY", "local-demo-key-change-before-deployment"),
                      MAX_CONTENT_LENGTH=MAX_UPLOAD, WTF_CSRF_ENABLED=True,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "false").lower() == "true")
    if test_config:
        app.config.update(test_config)
    CSRFProtect(app)
    app.config.setdefault("BOOKS_DIR", BOOKS_DIR)
    Path(app.config["BOOKS_DIR"]).mkdir(parents=True, exist_ok=True)
    db.initialize_database()

    def current_user():
        user_id = session.get("user_id")
        return db.get_user_by_id(user_id) if user_id else None

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user():
                flash("Please log in to continue.", "error")
                return redirect(url_for("login"))
            return view(*args, **kwargs)
        return wrapped

    def admin_required(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if session.get("role") != "Admin": abort(403)
            return view(*args, **kwargs)
        return wrapped

    @app.context_processor
    def inject_user():
        return {"logged_user": current_user()}

    @app.route("/")
    def index():
        if not current_user(): return redirect(url_for("login"))
        return redirect(url_for("admin_dashboard" if session.get("role") == "Admin" else "user_dashboard"))

    @app.route("/manifest.webmanifest")
    def web_manifest():
        return app.send_static_file("manifest.webmanifest")

    @app.route("/service-worker.js")
    def service_worker():
        response = app.send_static_file("service-worker.js")
        response.headers["Service-Worker-Allowed"] = "/"
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            user = db.get_user_by_email(request.form.get("email", ""))
            if user and check_password_hash(str(user.get("Password_Hash") or ""), request.form.get("password", "")):
                session.clear()
                session["user_id"], session["role"] = user["User_ID"], user["Role"]
                return redirect(url_for("admin_dashboard" if user["Role"] == "Admin" else "user_dashboard"))
            flash("Email or password is incorrect.", "error")
        return render_template("login.html")

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if request.method == "POST":
            name, email = request.form.get("name", "").strip(), request.form.get("email", "").strip()
            password, confirm = request.form.get("password", ""), request.form.get("confirm_password", "")
            if not name or not email or not password: flash("Please complete all required fields.", "error")
            elif password != confirm: flash("Passwords do not match.", "error")
            else:
                try:
                    db.add_user(name, email, password, "User")
                    flash("Account created. Please log in.", "success")
                    return redirect(url_for("login"))
                except db.DatabaseError as exc: flash(str(exc), "error")
        return render_template("signup.html")

    @app.route("/logout", methods=["POST"])
    def logout():
        session.clear()
        flash("You have been logged out.", "success")
        return redirect(url_for("login"))

    @app.route("/admin")
    @admin_required
    def admin_dashboard():
        books, users, feedback = db.get_all_books(), db.get_all_users(), db.get_all_feedback()
        return render_template("admin_dashboard.html", book_count=len(books), student_count=sum(u.get("Role") == "User" for u in users), feedback_count=len(feedback), pending_count=sum(f.get("Status") == "Pending" for f in feedback))

    @app.route("/dashboard")
    @login_required
    def user_dashboard():
        if session.get("role") == "Admin": return redirect(url_for("admin_dashboard"))
        return render_template("user_dashboard.html")

    @app.route("/books")
    @login_required
    def books():
        return render_template("books.html", books=db.search_books(request.args.get("q", "")), query=request.args.get("q", ""))

    @app.route("/books/add", methods=["GET", "POST"])
    @admin_required
    def add_book():
        if request.method == "POST":
            upload = request.files.get("pdf")
            if not all(request.form.get(field, "").strip() for field in ("title", "author", "category")):
                flash("Title, author and category are required.", "error")
            elif not upload or not upload.filename:
                flash("Choose a PDF file.", "error")
            else:
                content = upload.stream.read()
                if not content: flash("The selected PDF is empty.", "error")
                elif len(content) > MAX_UPLOAD: flash("PDF files must be 10 MB or smaller.", "error")
                elif not upload.filename.lower().endswith(".pdf") or not content.startswith(b"%PDF-"):
                    flash("Upload a valid PDF file.", "error")
                else:
                    try:
                        # The helper creates the ID and records its corresponding safe path.
                        book_id = db.add_book(request.form["title"], request.form["author"], request.form["category"], request.form.get("description", ""), "AUTO")
                    except db.DatabaseError as exc:
                        flash(str(exc), "error")
                        return render_template("add_book.html")
                    pdf_path = Path(app.config["BOOKS_DIR"]) / f"{book_id}.pdf"
                    pdf_path.write_bytes(content)
                    flash("Book added successfully.", "success")
                    return redirect(url_for("books"))
        return render_template("add_book.html")

    @app.route("/books/<book_id>/delete", methods=["POST"])
    @admin_required
    def remove_book(book_id):
        record = db.get_book_by_id(book_id)
        if not record:
            abort(404)
        expected = f"books/{book_id}.pdf"
        if record.get("PDF_Path") != expected:
            flash("Stored file path did not match this book; no file was removed.", "error")
            return redirect(url_for("books"))
        target = (Path(app.config["BOOKS_DIR"]) / f"{book_id}.pdf").resolve()
        if target.parent != Path(app.config["BOOKS_DIR"]).resolve():
            abort(400)
        db.delete_book(book_id)
        if target.is_file(): target.unlink()
        flash("Book deleted.", "success")
        return redirect(url_for("books"))

    @app.route("/books/<book_id>/read")
    @login_required
    def read_book(book_id):
        record = db.get_book_by_id(book_id)
        if not record: abort(404)
        expected = f"books/{book_id}.pdf"
        if record.get("PDF_Path") != expected: abort(404)
        target = (Path(app.config["BOOKS_DIR"]) / f"{book_id}.pdf").resolve()
        if target.parent != Path(app.config["BOOKS_DIR"]).resolve() or not target.is_file(): abort(404)
        return send_file(target, mimetype="application/pdf", as_attachment=False, download_name=f"{book_id}.pdf")

    @app.route("/admin/users")
    @admin_required
    def manage_users():
        return render_template("manage_users.html", users=[u for u in db.get_all_users() if u.get("Role") == "User"])

    @app.route("/admin/users/add", methods=["GET", "POST"])
    @admin_required
    def add_student():
        if request.method == "POST":
            if request.form.get("password") != request.form.get("confirm_password"):
                flash("Passwords do not match.", "error")
            else:
                try:
                    db.add_user(request.form.get("name"), request.form.get("email"), request.form.get("password"), "User")
                    flash("Student account created.", "success")
                    return redirect(url_for("manage_users"))
                except db.DatabaseError as exc: flash(str(exc), "error")
        return render_template("add_user.html")

    @app.route("/admin/users/<user_id>/reset", methods=["POST"])
    @admin_required
    def reset_password(user_id):
        user = db.get_user_by_id(user_id)
        if not user or user.get("Role") != "User": abort(404)
        password, confirm = request.form.get("password", ""), request.form.get("confirm_password", "")
        if not password: flash("A new password is required.", "error")
        elif password != confirm: flash("Passwords do not match.", "error")
        else:
            db.update_user_password(user_id, password)
            flash("Student password reset.", "success")
        return redirect(url_for("manage_users"))

    @app.route("/admin/users/<user_id>/delete", methods=["POST"])
    @admin_required
    def remove_user(user_id):
        if user_id == session.get("user_id"): abort(400)
        if not db.delete_user(user_id): abort(404)
        flash("Student account deleted. Feedback history was retained.", "success")
        return redirect(url_for("manage_users"))

    @app.route("/feedback", methods=["GET", "POST"])
    @login_required
    def feedback():
        if session.get("role") == "Admin": return redirect(url_for("admin_feedback"))
        if request.method == "POST":
            try:
                db.add_feedback(session["user_id"], request.form.get("message", ""))
                flash("Feedback submitted.", "success")
                return redirect(url_for("feedback"))
            except db.DatabaseError as exc: flash(str(exc), "error")
        return render_template("feedback.html", feedback=db.get_feedback_by_user(session["user_id"]))

    @app.route("/admin/feedback")
    @admin_required
    def admin_feedback():
        records = db.get_all_feedback()
        users = {u["User_ID"]: u for u in db.get_all_users()}
        for item in records:
            user = users.get(item.get("User_ID"))
            item["Student_Label"] = user.get("Name") if user else "Deleted User"
        return render_template("admin_feedback.html", feedback=records)

    @app.route("/admin/feedback/<feedback_id>/reply", methods=["POST"])
    @admin_required
    def reply_feedback(feedback_id):
        if not db.reply_to_feedback(feedback_id, request.form.get("reply", "")): abort(404)
        flash("Reply saved.", "success")
        return redirect(url_for("admin_feedback"))

    @app.route("/profile", methods=["GET", "POST"])
    @login_required
    def profile():
        user = current_user()
        if request.method == "POST":
            if not check_password_hash(user["Password_Hash"], request.form.get("current_password", "")):
                flash("Current password is incorrect.", "error")
            elif request.form.get("new_password") != request.form.get("confirm_password"):
                flash("New passwords do not match.", "error")
            elif not request.form.get("new_password"):
                flash("New password is required.", "error")
            else:
                db.update_user_password(user["User_ID"], request.form["new_password"])
                flash("Password changed.", "success")
                return redirect(url_for("profile"))
        return render_template("profile.html", user=user)

    @app.errorhandler(404)
    def not_found(error): return render_template("404.html"), 404

    @app.errorhandler(403)
    def forbidden(error): return render_template("403.html"), 403

    @app.errorhandler(413)
    def too_large(error):
        flash("PDF files must be 10 MB or smaller.", "error")
        return redirect(url_for("add_book"))

    @app.errorhandler(500)
    def server_error(error): return render_template("500.html"), 500

    return app


app = create_app()

if __name__ == "__main__":
    # Listen on the local network so a phone on the same Wi-Fi can reach the site.
    app.run(host="0.0.0.0", debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")
