export default async function run(page, ui) {
  const result = { steps: [], consoleErrors: [] };

  const seed = await page.evaluate(async () => {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        identifier: "QAADMIN01",
        password: "QaVerify123",
        role: "admin",
      }),
    });
    return { status: response.status, body: await response.text() };
  });
  result.steps.push({ loginViaApi: seed.status });

  await page.goto("http://127.0.0.1:5000/admin/dashboard");
  await page.waitForSelector('[data-admin-form="attendance"]', {
    timeout: 15000,
  });
  await page.waitForTimeout(2500);

  // The attendance form must exist and no giant student <select> should remain.
  result.attendanceForm = await page.evaluate(() => {
    const form = document.querySelector('[data-admin-form="attendance"]');
    return {
      exists: Boolean(form),
      personType: form?.dataset.personType,
      submitLabel: form?.querySelector('[type="submit"]')?.textContent?.trim(),
      hasSearchInputs: form?.querySelectorAll("[data-person-search-input]")
        .length,
      giantSelects: document.querySelectorAll("select option").length,
      statusOptions: Array.from(
        form?.querySelectorAll('[name="status"] option') || [],
      ).map((o) => o.value),
    };
  });

  // Search a student and confirm results come from the API.
  const studentSearch = page.locator('[data-person-search-input="student"]');
  await studentSearch.click();
  await studentSearch.fill("Rah");
  await page.waitForTimeout(900);
  result.studentSearch = await page.evaluate(() => {
    const list = document.querySelector(
      '[data-person-search-results="student"]',
    );
    return {
      visible: !list?.classList.contains("hidden"),
      count: list?.querySelectorAll('li[role="option"]').length,
      first: list?.querySelector("li p")?.textContent,
    };
  });

  // Pick the first result and confirm the selected chip appears.
  const firstOption = page
    .locator('[data-person-search-results="student"] li[role="option"]')
    .first();
  if (await firstOption.count()) {
    await firstOption.click();
    await page.waitForTimeout(400);
  }
  result.afterSelect = await page.evaluate(() => {
    const chip = document.querySelector('[data-person-selected="student"]');
    return {
      chipVisible: chip && !chip.classList.contains("hidden"),
      name: chip?.querySelector("[data-selected-name]")?.textContent,
      hiddenId: document.querySelector('[data-person-id="student"]')?.value,
    };
  });

  // Employee tab hides the course field and enables half day.
  await page.locator('[data-person-type-option][value="employee"]').check();
  await page.waitForTimeout(400);
  result.employeeTab = await page.evaluate(() => {
    const form = document.querySelector('[data-admin-form="attendance"]');
    const courseField = form.querySelector("[data-course-field]");
    const halfDay = form.querySelector("[data-employee-only]");
    return {
      employeePanelVisible: !form
        .querySelector('[data-person-search="employee"]')
        .classList.contains("hidden"),
      studentPanelHidden: form
        .querySelector('[data-person-search="student"]')
        .classList.contains("hidden"),
      courseHidden: courseField.classList.contains("hidden"),
      halfDayVisible: halfDay && !halfDay.hidden,
    };
  });

  const employeeSearch = page.locator('[data-person-search-input="employee"]');
  await employeeSearch.click();
  await employeeSearch.fill("EMP");
  await page.waitForTimeout(900);
  result.employeeSearch = await page.evaluate(() => {
    const list = document.querySelector(
      '[data-person-search-results="employee"]',
    );
    return {
      visible: !list?.classList.contains("hidden"),
      count: list?.querySelectorAll('li[role="option"]').length,
      first: list?.querySelector("li p")?.textContent,
    };
  });

  // Assignment create form + filters present.
  result.assignments = await page.evaluate(() => ({
    createForm: Boolean(
      document.querySelector('[data-admin-form="assignments"]'),
    ),
    filters: document.querySelectorAll("[data-assignment-filter]").length,
    rows: document.querySelectorAll("[data-admin-assignments] tr").length,
  }));

  // Attendance table renders with the person column.
  result.attendanceTable = await page.evaluate(() => {
    const head = document
      .querySelectorAll("[data-admin-attendance]")[0]
      ?.closest("table");
    return {
      columns: Array.from(head?.querySelectorAll("thead th") || []).map((th) =>
        th.textContent.trim(),
      ),
      rowCount: document.querySelectorAll("[data-admin-attendance] tr").length,
    };
  });

  return result;
}
