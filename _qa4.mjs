export default async function run(page, ui) {
  const out = {};
  const login = async (id, role) => {
    await page.evaluate(
      async ([i, r]) => {
        await fetch("/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            identifier: i,
            password: "QaVerify123",
            role: r,
          }),
        });
      },
      [id, role],
    );
  };

  // ---------- ADMIN: create an assignment through the UI ----------
  await login("QAADMIN01", "admin");
  await page.goto("http://127.0.0.1:5000/admin/dashboard");
  await page.waitForSelector('[data-admin-form="assignments"]', {
    timeout: 15000,
  });
  await page.waitForTimeout(2000);

  await page
    .locator('[data-admin-form="assignments"] [name="title"]')
    .fill("QA HTML Portfolio");
  await page
    .locator('[data-admin-form="assignments"] [name="description"]')
    .fill("Build a responsive personal portfolio page.");
  await page.locator('[data-person-search-input="assignment-course"]').click();
  await page
    .locator('[data-person-search-input="assignment-course"]')
    .fill("Advance Excel");
  await page.waitForTimeout(1000);
  await page
    .locator(
      '[data-person-search-results="assignment-course"] li[role="option"]',
    )
    .first()
    .click();
  await page.waitForTimeout(400);
  await page
    .locator('[data-admin-form="assignments"] [name="due_date"]')
    .fill("2026-12-20");
  await page.locator('[data-admin-form="assignments"] [type="submit"]').click();
  await page.waitForTimeout(2500);

  out.adminCreate = await page.evaluate(() => ({
    status: document
      .querySelector('[data-admin-form="assignments"] [data-form-status]')
      ?.textContent?.trim(),
    rows: Array.from(
      document.querySelectorAll("[data-admin-assignments] tr"),
    ).map((r) =>
      Array.from(r.querySelectorAll("td"))
        .slice(0, 5)
        .map((c) => c.textContent.trim()),
    ),
  }));

  // ---------- STUDENT dashboard ----------
  await login("QASTU0001", "student");
  await page.goto("http://127.0.0.1:5000/student/dashboard");
  await page.waitForSelector("[data-student-assignments]", { timeout: 15000 });
  await page.waitForTimeout(2500);
  out.student = await page.evaluate(() => ({
    assignments: Array.from(
      document.querySelectorAll("[data-student-assignments] tr"),
    ).map((r) =>
      Array.from(r.querySelectorAll("td")).map((c) => c.textContent.trim()),
    ),
    attendance: Array.from(
      document.querySelectorAll("[data-student-attendance] tr"),
    ).map((r) =>
      Array.from(r.querySelectorAll("td")).map((c) => c.textContent.trim()),
    ),
    assignmentCount: document.querySelector("[data-assignment-count]")
      ?.textContent,
    attendanceSummary: document.querySelector("[data-attendance-summary]")
      ?.textContent,
  }));

  // ---------- EMPLOYEE dashboard ----------
  await login("QAEMP0001", "employee");
  await page.goto("http://127.0.0.1:5000/employee/dashboard");
  await page.waitForSelector("[data-employee-assignment-list]", { timeout: 15000 });
  await page.waitForTimeout(2500);
  out.employee = await page.evaluate(() => ({
    assignments: Array.from(
      document.querySelectorAll("[data-employee-assignment-list] tr"),
    ).map((r) =>
      Array.from(r.querySelectorAll("td")).map((c) => c.textContent.trim()),
    ),
    attendance: Array.from(
      document.querySelectorAll("[data-employee-attendance] tr"),
    ).map((r) =>
      Array.from(r.querySelectorAll("td")).map((c) => c.textContent.trim()),
    ),
    assignmentCount: document.querySelector("[data-assignment-count]")
      ?.textContent,
  }));

  return out;
}
