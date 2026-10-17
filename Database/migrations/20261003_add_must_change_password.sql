USE dm_skill_institute;

ALTER TABLE users
  ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT FALSE
  AFTER auth_version;
