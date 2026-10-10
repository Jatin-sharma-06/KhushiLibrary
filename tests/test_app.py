import io
import tempfile
import unittest
from pathlib import Path

import database as db

# app.py creates the Flask app on import; point that startup initialization at
# a temporary workbook so the real project workbook is never touched by tests.
_import_temp = tempfile.TemporaryDirectory()
db.DATABASE_PATH = Path(_import_temp.name) / "import-test.xlsx"
from app import create_app


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = db.DATABASE_PATH
        db.DATABASE_PATH = Path(self.temp.name) / "app-test.xlsx"
        db.initialize_database()
        self.app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "SECRET_KEY": "test", "BOOKS_DIR": Path(self.temp.name) / "books"})
        self.client = self.app.test_client()
        self.student_id = db.add_user("Test Student", "student@example.com", "Student@1")

    def tearDown(self):
        db.DATABASE_PATH = self.old_path
        self.temp.cleanup()

    def login(self, email, password):
        return self.client.post("/login", data={"email": email, "password": password}, follow_redirects=True)

    def test_login_signup_role_and_logout(self):
        response = self.login("admin@gmail.com", "wrong")
        self.assertIn(b"incorrect", response.data)
        response = self.login("admin@gmail.com", "Admin@123")
        self.assertIn(b"Administrator dashboard", response.data)
        self.client.post("/logout")
        self.assertEqual(self.client.get("/admin").status_code, 302)
        self.client.post("/signup", data={"name": "New Student", "email": "new@example.com", "password": "abc", "confirm_password": "mismatch"})
        self.assertIsNone(db.get_user_by_email("new@example.com"))
        self.client.post("/signup", data={"name": "New Student", "email": "new@example.com", "password": "abc", "confirm_password": "abc"})
        self.assertEqual(db.get_user_by_email("new@example.com")["Role"], "User")

    def test_role_checks_books_and_feedback_ownership(self):
        self.assertEqual(self.client.get("/books").status_code, 302)
        self.login("student@example.com", "Student@1")
        self.assertEqual(self.client.get("/admin/users").status_code, 403)
        self.assertEqual(self.client.get("/admin/feedback").status_code, 403)
        response = self.client.post("/feedback", data={"message": "Hello library"}, follow_redirects=True)
        self.assertIn(b"Hello library", response.data)
        self.client.post("/logout")
        other_id = db.add_user("Other Student", "other@example.com", "Other@1")
        self.assertEqual(db.get_feedback_by_user(other_id), [])

    def test_mobile_app_manifest_and_service_worker(self):
        manifest = self.client.get("/manifest.webmanifest")
        self.assertEqual(manifest.status_code, 200)
        self.assertIn(b'"display": "standalone"', manifest.data)
        manifest.close()
        worker = self.client.get("/service-worker.js")
        self.assertEqual(worker.status_code, 200)
        self.assertEqual(worker.headers.get("Service-Worker-Allowed"), "/")
        worker.close()

    def test_pdf_upload_and_protected_read(self):
        self.login("admin@gmail.com", "Admin@123")
        response = self.client.post("/books/add", data={"title": "Guide", "author": "Author", "category": "Study", "pdf": (io.BytesIO(b"%PDF-1.4\nfile"), "guide.pdf")}, content_type="multipart/form-data", follow_redirects=True)
        self.assertIn(b"Guide", response.data)
        record = db.get_all_books()[0]
        # The PDF root is the project books folder for route tests; confirm the ID-bound route path is used.
        target = Path(self.app.config["BOOKS_DIR"]) / f"{record['Book_ID']}.pdf"
        self.assertTrue(target.is_file())
        read = self.client.get(f"/books/{record['Book_ID']}/read")
        self.assertEqual(read.status_code, 200)
        self.assertEqual(read.mimetype, "application/pdf")
        read.close()
        invalid = self.client.post("/books/add", data={"title": "Bad", "author": "Author", "category": "Study", "pdf": (io.BytesIO(b"not a PDF"), "bad.pdf")}, content_type="multipart/form-data")
        self.assertIn(b"valid PDF", invalid.data)
        deleted = self.client.post(f"/books/{record['Book_ID']}/delete", follow_redirects=True)
        self.assertIn(b"Book deleted", deleted.data)
        self.assertFalse(target.exists())

    def test_admin_user_management_and_profile_password(self):
        self.login("admin@gmail.com", "Admin@123")
        self.assertIn(b"Test Student", self.client.get("/admin/users").data)
        self.client.post(f"/admin/users/{self.student_id}/reset", data={"password": "Reset@1", "confirm_password": "Reset@1"})
        self.client.post("/logout")
        self.login("student@example.com", "Reset@1")
        page = self.client.get("/profile")
        self.assertIn(b"Test Student", page.data)
        bad = self.client.post("/profile", data={"current_password": "wrong", "new_password": "New@1", "confirm_password": "New@1"}, follow_redirects=True)
        self.assertIn(b"Current password is incorrect", bad.data)
        mismatch = self.client.post("/profile", data={"current_password": "Reset@1", "new_password": "New@1", "confirm_password": "Nope"}, follow_redirects=True)
        self.assertIn(b"do not match", mismatch.data)
        good = self.client.post("/profile", data={"current_password": "Reset@1", "new_password": "New@1", "confirm_password": "New@1"}, follow_redirects=True)
        self.assertIn(b"Password changed", good.data)

    def test_admin_cannot_delete_self_and_feedback_admin_reply(self):
        self.login("student@example.com", "Student@1")
        self.client.post("/feedback", data={"message": "Question"})
        self.client.post("/logout")
        self.login("admin@gmail.com", "Admin@123")
        admin_id = db.get_user_by_email("admin@gmail.com")["User_ID"]
        self.assertEqual(self.client.post(f"/admin/users/{admin_id}/delete").status_code, 400)
        self.assertIn(b"Question", self.client.get("/admin/feedback").data)
        feedback_id = db.get_all_feedback()[0]["Feedback_ID"]
        self.client.post(f"/admin/feedback/{feedback_id}/reply", data={"reply": "Answered"})
        self.assertEqual(db.get_all_feedback()[0]["Status"], "Replied")


if __name__ == "__main__": unittest.main()
