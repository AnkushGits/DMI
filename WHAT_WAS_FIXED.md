# What was found and fixed in D.M.I.zip

All of this was tested on a real MySQL-compatible database, not only read.

| # | Problem | Effect | Fix |
|---|---|---|---|
| 1 | `Database/schema.sql` was only 3 lines. It created an empty database and **no tables**. | Seed failed, create-admin failed, every page that uses the database failed. | Full schema written (15 tables) from what the code needs. Safe to run again. |
| 2 | `cursor.connection` does not exist in the fast MySQL driver (the Windows install has it). | `create_admin` crashed, and so would login, admin create, and the popup save. | `Backend/db.py` now gives every cursor a `.connection`. |
| 3 | `start_transaction()` ran after the login check query had already started a transaction. | Creating a student or a teacher failed with "Transaction already in progress". | `Backend/db.py` ends that read-only transaction first. |
| 4 | `Frontend/admin/login.html` and `admin/dashboard.html` had one missing `}` in the Tailwind settings. | JavaScript error. The brand green colours did not load on the admin pages. | Added the missing `}`. |
| 5 | `.env.example` was missing but README tells you to copy it. | The setup step fails. | Added `.env.example`. |
| 6 | The zip contained your real `.env` and a Windows `venv` folder (about 100 MB). | Secrets can leak. The venv does not work on other computers. | Removed from this package. See the notes below. |

## Please also do these (settings, not code)

- Your old `.env` used the MySQL **root** user, a SECRET_KEY that looks like placeholder text, and still had `ADMIN_INITIAL_PASSWORD`. Use the `dm_app` user, a random SECRET_KEY, and delete the admin password line after creating the admin.
- You shared the zip with a real `.env` inside. If it went to anyone else, change the MySQL root password and the admin password.
- Your unit tests use a fake database, which is why they passed while bugs 2 and 3 existed. Real checks are listed in the chat reply.
