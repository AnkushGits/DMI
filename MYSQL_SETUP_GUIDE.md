# How to connect MySQL to this website (step by step, for Windows)

You do not need to know MySQL. Just follow the steps in order.

**The idea in one minute.** MySQL is a program that stores your data (students, teachers, courses, enquiries).
Your Flask backend talks to MySQL using a user name and password that you put in the `.env` file.
So you need 4 things: (1) MySQL installed, (2) tables created, (3) a MySQL user for the app, (4) the `.env` file filled in.

---

## Step 1. Install MySQL

1. Go to https://dev.mysql.com/downloads/installer/ and download **MySQL Installer for Windows** (the bigger file is fine).
2. Run it. Choose **Server only** (or **Developer Default** if you also want MySQL Workbench, a window to see your data).
3. Keep the default port **3306**.
4. When it asks for a **root password**, type a strong password and **write it down**. You cannot see it again later.
5. Keep "Start MySQL Server at system startup" ticked. Finish the installer.

**Check it is running:** press the Windows key, type `Services`, open it, find **MySQL80**. It must say **Running**.

## Step 2. Make the `mysql` command work in PowerShell

Open PowerShell and type:

```powershell
mysql --version
```

If you see a version number, go to Step 3.
If you see "mysql is not recognized", run this (it only works for this PowerShell window):

```powershell
$env:Path += ";C:\Program Files\MySQL\MySQL Server 8.0\bin"
mysql --version
```

## Step 3. Create the database and tables

In PowerShell, go to your project folder (the one that contains `README.md`):

```powershell
cd "C:\path\to\D.M.I"
Get-Content -Raw Database\schema.sql | mysql -u root -p
Get-Content -Raw Database\seed.sql   | mysql -u root -p dm_skill_institute
```

Each time it asks for a password, type your **root password** (you will not see the letters while typing, this is normal).

**Check it worked:**

```powershell
mysql -u root -p -e "USE dm_skill_institute; SHOW TABLES; SELECT name, fee FROM courses;"
```

You should see **15 tables** and **5 courses**. If you see 0 tables, your `schema.sql` is the old broken one (3 lines). Use the new one from this zip.

*Prefer clicking? Open MySQL Workbench, connect, choose File > Open SQL Script, pick `schema.sql`, click the lightning button. Then do the same with `seed.sql`.*

## Step 4. Create a MySQL user for the website (do not use root)

```powershell
mysql -u root -p
```

Now you are inside MySQL (the prompt changes to `mysql>`). Type these 3 lines. Change `YourLongPassword123` to your own password and write it down:

```sql
CREATE USER 'dm_app'@'localhost' IDENTIFIED BY '@Admin.DM123';
GRANT SELECT, INSERT, UPDATE, DELETE ON dm_skill_institute.* TO 'dm_app'@'localhost';
FLUSH PRIVILEGES;
```

Type `exit;` to leave.

## Step 5. Set up Python (new folder, do not use the old `Backend\venv`)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r Backend\requirements.txt
```

(If PowerShell blocks the activate script, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once and try again.)

## Step 6. Create your `.env` file

```powershell
Copy-Item .env.example .env
notepad .env
```

Fill in these lines and save:

| Line | What to write |
|---|---|
| `SECRET_KEY` | Run `python -c "import secrets; print(secrets.token_urlsafe(48))"` and paste the result |
| `DB_USER` | `dm_app` |
| `DB_PASSWORD` | the password you chose in Step 4 |
| `ADMIN_LOGIN_ID` | the ID you will use to log in as admin, for example `ADMIN001` |
| `ADMIN_INITIAL_PASSWORD` | a password with **12 or more** characters |

The file must be named exactly `.env` and sit in the same folder as `README.md`.

## Step 7. Create the first admin account

```powershell
python -m Backend.create_admin
```

You should see: `Admin account created for ...`.
Then open `.env` and **delete the `ADMIN_INITIAL_PASSWORD` line**.

## Step 8. Start the website

```powershell
python -m Backend.app
```

Open http://127.0.0.1:5000/health in your browser. It should show `{"status":"ok"}`.
Then open http://127.0.0.1:5000/admin/login and sign in with your admin ID and password.
If you can sign in, **MySQL is connected**.

---

## If something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| `Access denied for user` | Wrong `DB_USER` or `DB_PASSWORD` in `.env` | Check Step 4 and Step 6. The password must be exactly the same. |
| `Can't connect to MySQL server on '127.0.0.1:3306'` | MySQL is not running | Open Services, start **MySQL80**. |
| `Unknown database 'dm_skill_institute'` | Step 3 was not done | Run the schema command again. |
| `Table 'dm_skill_institute.users' doesn't exist` | Tables are missing (old 3-line schema) | Use the new `schema.sql`, repeat Step 3. |
| `mysql is not recognized` | Windows cannot find MySQL | Step 2. |
| `SECRET_KEY must be configured` | `.env` is missing or in the wrong folder | It must be next to `README.md`. |
| `No module named 'Backend'` | You ran the command from the wrong folder | Run from the folder with `README.md`, using `python -m Backend.app`. |
| Browser says "The service is temporarily unavailable." | The website cannot reach MySQL | Look at the PowerShell window where the app runs. The real error is printed there. |
| Login says "Too many requests" | Login limit is 5 tries per minute | Wait one minute. |

## Keep your data safe

- Never share `.env`. It holds your passwords.
- Back up the database now and then:
  `mysqldump -u root -p dm_skill_institute > backup.sql`
