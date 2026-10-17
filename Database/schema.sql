-- DM Skills Institute: database tables (MySQL 8.0 or newer)
-- Run this file ONE time. It is safe to run again: tables that exist are kept.
--
-- Windows PowerShell:
--   Get-Content -Raw Database\schema.sql | mysql -u root -p
--   Get-Content -Raw Database\seed.sql   | mysql -u root -p dm_skill_institute

CREATE DATABASE IF NOT EXISTS dm_skill_institute
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE dm_skill_institute;

-- ---------------------------------------------------------------
-- users: one login table for admin, student and employee.
-- Passwords are saved only as a hash (never as plain text).
-- auth_version goes up when a password changes, so old sessions stop working.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
  id            INT UNSIGNED NOT NULL AUTO_INCREMENT,
  login_id      VARCHAR(60)  NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  role          ENUM('admin','student','employee') NOT NULL,
  status        ENUM('active','inactive') NOT NULL DEFAULT 'active',
  auth_version  INT UNSIGNED NOT NULL DEFAULT 1,
  must_change_password BOOLEAN NOT NULL DEFAULT FALSE,
  last_login    DATETIME NULL,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_users_login_id (login_id),
  KEY idx_users_role (role)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS admins (
  id        INT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id   INT UNSIGNED NOT NULL,
  full_name VARCHAR(150) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_admins_user (user_id),
  CONSTRAINT fk_admins_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS courses (
  id              INT UNSIGNED NOT NULL AUTO_INCREMENT,
  course_code     VARCHAR(40)  NOT NULL,
  name            VARCHAR(180) NOT NULL,
  description     TEXT NULL,
  duration_months SMALLINT UNSIGNED NULL,
  fee             DECIMAL(10,2) NOT NULL DEFAULT 0.00,
  status          ENUM('active','inactive') NOT NULL DEFAULT 'active',
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_courses_code (course_code),
  UNIQUE KEY uq_courses_name (name),
  KEY idx_courses_name (name)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS students (
  id            INT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id       INT UNSIGNED NOT NULL,
  student_id    VARCHAR(60)  NOT NULL,              -- example: DM20260001
  full_name     VARCHAR(150) NOT NULL,
  father_name   VARCHAR(150) NULL,
  mother_name   VARCHAR(150) NULL,
  date_of_birth DATE NULL,
  gender        VARCHAR(30)  NULL,
  phone         VARCHAR(30)  NULL,
  email         VARCHAR(254) NULL,
  address       TEXT NULL,
  city          VARCHAR(100) NULL,
  admission_date DATE NULL,
  profile_photo VARCHAR(255) NULL,
  status        ENUM('active','inactive') NOT NULL DEFAULT 'active',
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_students_user (user_id),
  UNIQUE KEY uq_students_student_id (student_id),
  KEY idx_students_name (full_name),
  KEY idx_students_phone (phone),
  KEY idx_students_email (email),
  CONSTRAINT fk_students_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS employees (
  id            INT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id       INT UNSIGNED NOT NULL,
  employee_id   VARCHAR(60)  NOT NULL,              -- example: EMP1001
  full_name     VARCHAR(150) NOT NULL,
  phone         VARCHAR(30)  NULL,
  email         VARCHAR(254) NULL,
  address       TEXT NULL,
  designation   VARCHAR(120) NULL,
  department    VARCHAR(120) NULL,
  joining_date  DATE NULL,
  profile_photo VARCHAR(255) NULL,
  status        ENUM('active','inactive') NOT NULL DEFAULT 'active',
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_employees_user (user_id),
  UNIQUE KEY uq_employees_employee_id (employee_id),
  KEY idx_employees_name (full_name),
  KEY idx_employees_phone (phone),
  KEY idx_employees_email (email),
  KEY idx_employees_designation (designation),
  CONSTRAINT fk_employees_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Which courses a teacher teaches.
CREATE TABLE IF NOT EXISTS employee_courses (
  id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
  employee_id INT UNSIGNED NOT NULL,
  course_id   INT UNSIGNED NOT NULL,
  created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_employee_course (employee_id, course_id),
  CONSTRAINT fk_ec_employee FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
  CONSTRAINT fk_ec_course   FOREIGN KEY (course_id)   REFERENCES courses(id)   ON DELETE CASCADE
) ENGINE=InnoDB;

-- Which course a student joined, and which teacher takes them.
CREATE TABLE IF NOT EXISTS student_courses (
  id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
  student_id  INT UNSIGNED NOT NULL,
  course_id   INT UNSIGNED NOT NULL,
  employee_id INT UNSIGNED NULL,
  start_date  DATE NULL,
  status      ENUM('active','completed','withdrawn') NOT NULL DEFAULT 'active',
  created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_student_course (student_id, course_id),
  KEY idx_sc_employee (employee_id),
  CONSTRAINT fk_sc_student  FOREIGN KEY (student_id)  REFERENCES students(id)  ON DELETE CASCADE,
  CONSTRAINT fk_sc_course   FOREIGN KEY (course_id)   REFERENCES courses(id)   ON DELETE CASCADE,
  CONSTRAINT fk_sc_employee FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS attendance (
  id              INT UNSIGNED NOT NULL AUTO_INCREMENT,
  student_id      INT UNSIGNED NOT NULL,
  employee_id     INT UNSIGNED NULL,
  course_id       INT UNSIGNED NOT NULL,
  attendance_date DATE NOT NULL,
  status          ENUM('present','absent','late','leave','half_day') NOT NULL,
  remarks         VARCHAR(500) NULL,
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_attendance_day (student_id, course_id, attendance_date),
  KEY idx_att_employee (employee_id),
  KEY idx_attendance_date (attendance_date),
  KEY idx_attendance_course_date (course_id, attendance_date),
  CONSTRAINT fk_att_student  FOREIGN KEY (student_id)  REFERENCES students(id)  ON DELETE CASCADE,
  CONSTRAINT fk_att_employee FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE SET NULL,
  CONSTRAINT fk_att_course   FOREIGN KEY (course_id)   REFERENCES courses(id)   ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS assignments (
  id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
  title       VARCHAR(200) NOT NULL,
  description TEXT NULL,
  course_id   INT UNSIGNED NOT NULL,
  created_by  INT UNSIGNED NULL,                    -- users.id of the teacher
  due_date    DATE NULL,
  attachment  VARCHAR(500) NULL,
  status      ENUM('active','draft','closed') NOT NULL DEFAULT 'active',
  created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_asg_course (course_id),
  KEY idx_assignments_due_date (due_date),
  CONSTRAINT fk_asg_course FOREIGN KEY (course_id)  REFERENCES courses(id) ON DELETE CASCADE,
  CONSTRAINT fk_asg_user   FOREIGN KEY (created_by) REFERENCES users(id)   ON DELETE SET NULL
) ENGINE=InnoDB;

-- Employee attendance is separate from student attendance: a staff member is
-- marked for a day, not per course. Uniqueness is employee + date.
CREATE TABLE IF NOT EXISTS employee_attendance (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  employee_id     BIGINT UNSIGNED NOT NULL,
  attendance_date DATE NOT NULL,
  status          ENUM('present','absent','late','leave','half_day') NOT NULL,
  remarks         VARCHAR(500) NULL,
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_employee_attendance_day (employee_id, attendance_date),
  KEY idx_employee_attendance_date (attendance_date),
  CONSTRAINT fk_emp_att_employee FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- For the future: students handing in their work.
CREATE TABLE IF NOT EXISTS assignment_submissions (
  id            INT UNSIGNED NOT NULL AUTO_INCREMENT,
  assignment_id INT UNSIGNED NOT NULL,
  student_id    INT UNSIGNED NOT NULL,
  file_url      VARCHAR(500) NULL,
  notes         TEXT NULL,
  marks         DECIMAL(5,2) NULL,
  submitted_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_submission (assignment_id, student_id),
  CONSTRAINT fk_sub_assignment FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE CASCADE,
  CONSTRAINT fk_sub_student    FOREIGN KEY (student_id)    REFERENCES students(id)    ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS study_materials (
  id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
  title       VARCHAR(200) NOT NULL,
  description TEXT NULL,
  course_id   INT UNSIGNED NOT NULL,
  uploaded_by INT UNSIGNED NULL,                    -- users.id
  file_url    VARCHAR(500) NOT NULL,
  created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_mat_course (course_id),
  CONSTRAINT fk_mat_course FOREIGN KEY (course_id)   REFERENCES courses(id) ON DELETE CASCADE,
  CONSTRAINT fk_mat_user   FOREIGN KEY (uploaded_by) REFERENCES users(id)   ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS announcements (
  id           INT UNSIGNED NOT NULL AUTO_INCREMENT,
  title        VARCHAR(200) NOT NULL,
  body         TEXT NOT NULL,
  audience     ENUM('all','student','employee') NOT NULL DEFAULT 'all',
  course_id    INT UNSIGNED NULL,                   -- empty means for every course
  created_by   INT UNSIGNED NULL,
  published_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_ann_published (published_at),
  CONSTRAINT fk_ann_course FOREIGN KEY (course_id)  REFERENCES courses(id) ON DELETE CASCADE,
  CONSTRAINT fk_ann_user   FOREIGN KEY (created_by) REFERENCES users(id)   ON DELETE SET NULL
) ENGINE=InnoDB;

-- People who fill the enquiry popup on the website.
CREATE TABLE IF NOT EXISTS fees (
  id             INT UNSIGNED NOT NULL AUTO_INCREMENT,
  student_id     INT UNSIGNED NOT NULL,
  course_id      INT UNSIGNED NULL,
  amount         DECIMAL(10,2) NOT NULL,
  paid_amount    DECIMAL(10,2) NOT NULL DEFAULT 0.00,
  due_amount     DECIMAL(10,2) NOT NULL DEFAULT 0.00,
  payment_date   DATE NULL,
  payment_status ENUM('paid','partial','pending') NOT NULL DEFAULT 'pending',
  remarks        VARCHAR(255) NULL,
  created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_fees_student (student_id),
  CONSTRAINT fk_fees_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
  CONSTRAINT fk_fees_course  FOREIGN KEY (course_id)  REFERENCES courses(id)  ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS results (
  id         INT UNSIGNED NOT NULL AUTO_INCREMENT,
  student_id INT UNSIGNED NOT NULL,
  course_id  INT UNSIGNED NOT NULL,
  subject    VARCHAR(150) NOT NULL,
  marks      DECIMAL(5,2) NOT NULL,
  grade      VARCHAR(5) NULL,
  exam_date  DATE NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_results_student (student_id),
  CONSTRAINT fk_res_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
  CONSTRAINT fk_res_course  FOREIGN KEY (course_id)  REFERENCES courses(id)  ON DELETE CASCADE
) ENGINE=InnoDB;
