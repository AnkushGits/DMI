-- Run once. Safe to run again.
--
-- 1. Employee attendance is a separate business object from student attendance:
--    an employee is marked present for a day, not for a student/course pair.
--    Uniqueness is employee + date.
-- 2. Search indexes for the database-backed autocomplete endpoints.
-- 3. Half day is part of this institute's attendance policy.
-- 4. Assignments gain a 'draft' state so an admin can prepare work before
--    students see it. 'overdue' is derived from due_date, never stored.
-- 5. attendance.employee_id is nullable. schema.sql always declared it NULL,
--    but the live table was created NOT NULL, which made it impossible to mark a
--    student present when no teacher had been assigned to their course.
--
-- NOTE: the live database was created with BIGINT UNSIGNED key columns, not the
-- INT UNSIGNED written in schema.sql. The types here match the existing
-- employees.id, because a foreign key must reference an identical column type.

USE dm_skill_institute;

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

-- 'half day' is only offered for employees, so student attendance keeps its own
-- status list untouched.
SET @half_day_exists = (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance' AND COLUMN_NAME = 'half_day'
);
SET @alter = IF(@half_day_exists = 0,
  'ALTER TABLE attendance MODIFY status ENUM(''present'',''absent'',''late'',''leave'',''half_day'') NOT NULL',
  'DO 0');
PREPARE stmt FROM @alter;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Autocomplete searches student_id / full_name / phone / email.
-- student_id and full_name already have indexes; these cover phone and email.
CREATE INDEX idx_students_phone ON students (phone);
CREATE INDEX idx_students_email ON students (email);
CREATE INDEX idx_employees_phone ON employees (phone);
CREATE INDEX idx_employees_email ON employees (email);
CREATE INDEX idx_employees_designation ON employees (designation);
CREATE INDEX idx_courses_name ON courses (name);

-- Attendance history is filtered by person + date range.
CREATE INDEX idx_attendance_date ON attendance (attendance_date);
CREATE INDEX idx_attendance_course_date ON attendance (course_id, attendance_date);
CREATE INDEX idx_assignments_due_date ON assignments (due_date);

SET @draft_exists = (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'assignments'
    AND COLUMN_TYPE LIKE '%''draft''%'
);
SET @alter_status = IF(@draft_exists = 0,
  'ALTER TABLE assignments MODIFY status ENUM(''active'',''draft'',''closed'') NOT NULL DEFAULT ''active''',
  'DO 0');
PREPARE stmt_status FROM @alter_status;
EXECUTE stmt_status;
DEALLOCATE PREPARE stmt_status;

SET @emp_null = (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance'
    AND COLUMN_NAME = 'employee_id' AND IS_NULLABLE = 'NO'
);
SET @alter_employee = IF(@emp_null = 1,
  'ALTER TABLE attendance MODIFY employee_id BIGINT UNSIGNED NULL DEFAULT NULL',
  'DO 0');
PREPARE stmt_employee FROM @alter_employee;
EXECUTE stmt_employee;
DEALLOCATE PREPARE stmt_employee;
