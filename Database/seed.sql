USE dm_skill_institute;

INSERT IGNORE INTO courses (course_code, name, description, duration_months, fee) VALUES
  ('MASTER-ACCOUNTANT', 'Master Accountant using Tally', 'Comprehensive master accounting program, advanced Tally Prime, complete taxation, balance sheet, corporate accounting and financial auditing.', 12, 50000.00),
  ('TALLY-PRO', 'Tally Professional', 'Professional accounting and ledgers, multi-currency and cost centres, inventory and order processing, lab practical and certification.', 12, 30000.00),
  ('GST-TALLY', 'GST using Tallyprime', 'Practical GST compliance, GSTR return filing, e-Way bills, e-Invoicing and GST portal reconciliation using Tally Prime.', 3, 8000.00),
  ('ADV-EXCEL', 'Advance Excel', 'Advanced Excel training including VLOOKUP, XLOOKUP, INDEX-MATCH, interactive pivot tables and charts.', 3, 4500.00),
  ('RS-CIT', 'RS-CIT', 'Rajasthan State Certificate in Information Technology (RS-CIT) course.', 3, 4500.00);
