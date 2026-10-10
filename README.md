# Library Management System

It stores students, books, and feedback in an Excel workbook so the complete data flow is easy to demonstrate.

## Features

- Student signup and login, plus an administrator account seeded once at workbook initialization.
- Separate administrator and student dashboards with server-side access checks.
- Book search, PDF upload, protected in-browser PDF reading, and safe book deletion.
- Student account creation, password reset, and account deletion by the administrator.
- Private student feedback history and administrator replies.
- Profile details and password changes with current-password verification.
- CSRF protection on forms and hashed passwords.
- Installable mobile web app (PWA) for adding the student library to a phone's home screen.

## Technologies and files

Python, Flask, Jinja2, HTML/CSS, `openpyxl`, Flask-WTF, and `python-dotenv`.

```text
LibraryManagementSystem/
  app.py                 Flask routes and validation
  database.py            Excel workbook functions
  library_database.xlsx  Created automatically; do not edit while app is running
  books/                 Uploaded PDFs (named by book ID)
  static/style.css       Responsive styling
  static/manifest.webmanifest Mobile app name, icon, and display settings
  static/service-worker.js Caches only static app resources
  static/profiles/       Default profile image
  templates/             Jinja HTML pages
  tests/                 unittest coverage
  .env.example           Environment variable example
```

## Windows setup in VS Code

Prerequisites: Python 3.10 or newer and VS Code with the Python extension.

Open this folder in VS Code, choose **Terminal → New Terminal**, and run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then activate the environment again. Edit `.env` and set a long random `SECRET_KEY`. The demonstration admin values can be changed with `INITIAL_ADMIN_EMAIL` and `INITIAL_ADMIN_PASSWORD`. These values are used only when the first administrator is created. Changing them after the admin exists does not reset the account password.

Initialize the workbook by starting the application. Initialization also runs automatically on every startup, preserves existing rows, ensures the three required worksheets exist, and seeds the administrator only when its configured email is absent.

```powershell
python app.py
```

Open <http://127.0.0.1:5000>. Stop the server with Ctrl+C. For local demonstration, sign in with `admin@gmail.com` / `Admin@123` unless you configured different credentials before the first workbook initialization. Change the demonstration password from the Profile page before any real deployment. Students can create accounts through **Sign up**. Administrators add books through **Books → Add book** and upload PDFs up to 10 MB.

## Use it on a student's phone

The app is a mobile web app, so it does not need to be installed from an app store. To try it at home on the same Wi-Fi:

1. Start the Flask server on the computer with `python app.py`.
2. On Windows, run `ipconfig` and note the computer's **IPv4 Address** (for example, `192.168.1.25`). If Windows Firewall asks, allow Python on your private network.
3. On the phone connected to that same Wi-Fi, open `http://COMPUTER-IP:5000` (replace `COMPUTER-IP` with the IPv4 address).
4. Sign in with her student email and password, or register first.

To install it as an app icon, serve the site over HTTPS, then open it in Chrome on Android or Safari on iPhone. On Android choose **Install app** or **Add to Home screen** in the browser menu. On iPhone in Safari tap **Share → Add to Home Screen**. The computer/server must remain running for the phone to use the library. The PWA keeps static styling and icons cached; account pages, books, and PDFs need an internet connection to the server. For use away from home Wi-Fi, deploy the Flask app to a server with HTTPS.

## Workbook schema

The project workbook has exactly three sheets: `Users` (`User_ID`, `Name`, `Email`, `Password_Hash`, `Role`, `Profile_Image`); `Books` (`Book_ID`, `Title`, `Author`, `Category`, `Description`, `PDF_Path`, `Date_Added`); and `Feedback` (`Feedback_ID`, `User_ID`, `Message`, `Admin_Reply`, `Date_Submitted`, `Status`). Passwords are stored as Werkzeug hashes. Feedback rows remain after a student account is deleted.

## Tests

```powershell
python -m unittest discover -s tests -v
```

The tests use a temporary workbook and temporary data where possible. Avoid editing the live workbook in Excel while the website is running.

## Troubleshooting and limitations

- **Missing package:** activate `.venv` and run `pip install -r requirements.txt`.
- **Workbook cannot be saved:** close `library_database.xlsx` in Excel and restart the website.
- **Admin login fails:** verify the configured email/password; environment seed settings apply only when creating the initial admin.
- **PDF will not open:** ensure the file begins with a PDF signature and is no larger than 10 MB.
- Flask's built-in server and this Excel database are for a small local demonstration. Excel does not provide database transactions or safe multi-process concurrent writes; only one app process should write to the workbook at a time.
- The demonstration secret and credentials must be replaced before deployment. Use HTTPS and set `COOKIE_SECURE=true` behind HTTPS. The local default secret is for development only.
- The application uses basic password rules and does not implement email verification, rate limiting, backups, audit logging, or multi-user database concurrency.
