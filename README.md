# DM Skills Institute

This project keeps the existing DM Skills Institute public website and Flask + MySQL portal organized into `Frontend/`, `Backend/`, and `Database/`. The management portal uses database-backed accounts, Werkzeug password hashes, signed HttpOnly session cookies, CSRF tokens for state-changing requests, role checks on protected API routes, and rate-limited login attempts.

## Requirements

- Python 3.10 or newer
- MySQL 8.0 or newer
- A current browser

## Project structure

```text
Frontend/
  index.html and public pages
  admin/        admin login and dashboard
  student/      student login and dashboard
  employee/     employee login and dashboard
  css/          site stylesheets
  js/           portal and admission scripts
  assets/images/
Backend/
  app.py, config.py, db.py, requirements.txt
  routes/       auth, admin, portal, and public APIs
  tests/
Database/
  schema.sql
  seed.sql
.env.example
.gitignore
README.md
```

## Local setup

Run these commands from the project root in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r Backend\requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set a unique `SECRET_KEY`, the local MySQL connection values, and the initial admin values. Do not publish `.env`.

The schema script creates the database and normalized tables:

```powershell
Get-Content -Raw Database\schema.sql | mysql -u root -p
Get-Content -Raw Database\seed.sql | mysql -u root -p dm_skill_institute
```

For an existing database, apply the additive first-login migration once before starting or upgrading the app. The application reads this column for authentication, so upgrade existing databases before deploying the new code:

```powershell
Get-Content -Raw Database\migrations\20261003_add_must_change_password.sql | mysql -u root -p
```

Fresh databases created from the current schema already include this column; do not apply the migration to them.

The seed contains the five existing course names and their currently advertised offer fees from `courses.html`. It is safe to run more than once and does not overwrite edits made in the admin portal.

Create a dedicated database account after creating the schema rather than using MySQL's root account in application deployments:

```sql
CREATE USER 'dm_app'@'localhost' IDENTIFIED BY 'choose-a-long-unique-password';
GRANT SELECT, INSERT, UPDATE, DELETE
  ON dm_skill_institute.* TO 'dm_app'@'localhost';
```

Create the first admin using the values in `.env`:

```powershell
python -m Backend.create_admin
```

After creating the first account, remove `ADMIN_INITIAL_PASSWORD` from `.env` and keep the real admin credential in a secure password manager. The create-admin command is a local CLI command, not a public setup API.

## Development

```powershell
python -m Backend.app
```

Open `http://127.0.0.1:5000/`. Flask serves the HTML and assets from `Frontend/` so API calls and secure session cookies remain same-origin. There is no separate frontend server command; the backend start command serves the complete frontend.

Portal routes:

- Public website: `/`
- Admin login/dashboard: `/admin/login`, `/admin/dashboard`
- Student login/dashboard: `/student/login`, `/student/dashboard`
- Employee login/dashboard: `/employee/login`, `/employee/dashboard`

The existing `.html` portal links are also served for compatibility.

## API overview

All JSON API endpoints are under `/api`. State-changing authenticated endpoints require the `X-CSRF-Token` returned by login or `/api/auth/me`.

| Method | Endpoint | Access |
|---|---|---|
| POST | `/api/auth/login` | Public; requires identifier, password, and role |
| POST | `/api/auth/logout` | Authenticated |
| GET | `/api/auth/me` | Authenticated |
| POST | `/api/auth/change-password` | Authenticated; also required before first use after account creation/reset |
| GET | `/api/courses` | Public active course catalog |
| GET | `/api/chat/faqs` | Public DEMOE preset questions |
| POST | `/api/chat` | Public rate-limited DEMOE response (`message`, optional short `history`) |
| POST | `/api/admissions` | Public, rate limited; records an admission lead |
| GET | `/api/admin/dashboard` | Admin |
| GET/POST | `/api/admin/students` | Admin |
| PUT | `/api/admin/students/<id>` | Admin |
| DELETE | `/api/admin/students/<id>` | Admin; requires JSON `{"confirmation":"DELETE"}`; permanently deletes student and cascaded records |
| POST | `/api/admin/students/<id>/reset-password` | Admin |
| GET/POST | `/api/admin/employees` | Admin |
| PUT | `/api/admin/employees/<id>` | Admin |
| DELETE | `/api/admin/employees/<id>` | Admin; requires JSON `{"confirmation":"DELETE"}`; permanently deletes employee account |
| POST | `/api/admin/employees/<id>/reset-password` | Admin |
| GET/POST | `/api/admin/courses` | Admin |
| PUT | `/api/admin/courses/<id>` | Admin |
| GET | `/api/admin/admissions` | Admin |
| PUT | `/api/admin/admissions/<id>` | Admin |
| GET/POST | `/api/admin/attendance` | Admin; attendance conflicts return 409 |
| PUT/DELETE | `/api/admin/attendance/<id>` | Admin |
| GET | `/api/admin/assignments`, `/materials`, `/fees`, `/results`, `/announcements` | Admin |
| POST | `/api/admin/fees`, `/results`, `/announcements` | Admin |
| GET | `/api/portal/overview`, `/profile`, `/courses`, `/attendance`, `/assignments`, `/materials`, `/announcements` | Student/employee, scoped to role and account |
| PUT | `/api/portal/profile` | Student/employee; phone, email, and address only |
| GET | `/api/portal/fees`, `/results` | Student, own account only |
| GET | `/api/portal/students` | Employee, assigned students only |
| POST | `/api/portal/assignments`, `/materials`, `/announcements` | Employee, assigned courses only |

IDs supplied to portal APIs are internal numeric row IDs unless an endpoint explicitly asks for a login identifier. Account access is checked against the authenticated database user and assigned course relationships; a browser-side role label is never treated as authorization.

## Database

`Database/schema.sql` creates normalized InnoDB tables: `users`, `admins`, `students`, `employees`, `courses`, `student_courses`, `employee_courses`, `attendance`, `assignments`, `assignment_submissions`, `study_materials`, `announcements`, `admission_leads`, `fees`, and `results`. Foreign keys and unique account/course relationships are defined in the schema.

Admin-created accounts receive generated IDs (`DM<year><student row id>` and `EMP<1000 + employee row id>`). A password and confirmation are required; passwords must contain at least eight characters, one letter, and one number. The admin form can generate a memorable password. The create/reset response returns the temporary password once, and newly created/reset accounts must change it before using protected portal features. Passwords are stored only as hashes. Students and employees can update only their own phone, email, and address; IDs, roles, status, and course assignments are read-only to them.

## Existing admission flow

The existing Google Apps Script submission remains in place. The popup also posts a copy to `/api/admissions` so the lead can be reviewed by an admin. A database-save failure is logged in the browser and does not block the original Google Sheets submission.

## DEMOE AI assistant
DEMOE appears on the eight public pages (not portal pages). Its four official fixed answers live in `Backend/services/demoe_service.py` and do not call OpenRouter or MySQL. Other questions use only public institute facts and the active `courses` database catalog; if MySQL is unavailable, DEMOE omits course-specific claims. Conversation history is limited to the current browser page and is not stored on the server. No admin FAQ editing is included in this release.

Set `OPENROUTER_API_KEY` and the owner-approved `OPENROUTER_MODEL` in the **backend** environment to enable AI answers. Without either, the four fixed answers still work and other questions return a safe availability message. Never put the key in HTML or JavaScript. For local testing, copy `.env.example` to `.env`; for production use a secrets manager and a shared rate-limit store (Redis through `RATELIMIT_STORAGE_URI`). The upstream request uses a 20-second timeout. Test real GPT-5 output and policy with a configured key before enabling in production.

## Production deployment

1. Deploy behind HTTPS with a production WSGI server (for example, Gunicorn behind Nginx or a managed Python host).
2. Set `COOKIE_SECURE=true`, a unique `SECRET_KEY`, production MySQL credentials, and a shared rate-limit store such as Redis through `RATELIMIT_STORAGE_URI`.
3. Configure MySQL network access, backups, least-privilege credentials, and TLS.
4. Set `FLASK_DEBUG=false`; do not expose development server or MySQL publicly.
5. Serve the project through Flask/WSGI at one origin or configure a reviewed same-origin reverse proxy for the API.
6. Verify HTTPS, cookie flags, backups, logs, schema upgrade procedure, and access-control behavior before onboarding real users.

The built-in rate limiter defaults to process memory for local development. Use a shared storage backend in multi-worker production. The current material API stores a file URL/reference; managed uploads and secure file delivery should be added before treating it as a production document-storage system.

## Implemented scope and limitations

- Existing public website pages, assets, course design, and Google Sheets admission popup are preserved in `Frontend/`.
- MySQL schema, admin provisioning command, secure authentication, role-scoped API foundations, student/employee/course creation and updates, password reset, admission lead capture, and dashboards backed by API data are included.
- Students can view their own profile, course, attendance, assignments, materials, fees, results, and announcements through scoped APIs.
- Employees can search and filter their assigned-student list, view assigned courses, and create assignments, materials, and announcements for assigned courses. Attendance is read-only to students and managed by admins.
- Admin dashboard supports overview; student, employee, and course creation/listing/editing; account activation/deactivation; confirmed permanent deletion; password resets; admission status updates; attendance creation/edit/deletion and filtering; and assignment, material, fee, result, and announcement views. Admins can record fees/results and publish announcements. Student/employee search and status/course filters query the admin APIs. Permanent student deletion cascades student-linked course, attendance, assignment submission, fee, and result records. Permanent employee deletion removes course assignments and the account; shared course content remains with its creator reference cleared, and student/attendance instructor links are set null by the schema. Assignment submissions, messaging, leave requests, certificates, and file upload storage remain future work.
- No demo accounts or frontend-only authentication are provided.

## Tests

Automated tests cover role enforcement, authentication-version invalidation, first-login password gating, password policy, account deletion confirmation, scoped profile edits, and admin attendance writes/conflicts. Run:

```powershell
python -m unittest discover -s Backend/tests -v
python -m compileall Backend
```

End-to-end account creation/login tests require the configured MySQL service, the first-login migration on existing databases, and a provisioned admin account.
