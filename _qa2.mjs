export default async function run(page, ui) {
  const out = {};
  await page.evaluate(async () => {
    await fetch('/api/auth/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ identifier: 'QAADMIN01', password: 'QaVerify123', role: 'admin' })
    });
  });
  await page.goto('http://127.0.0.1:5000/admin/dashboard');
  await page.waitForSelector('[data-admin-form="attendance"]', { timeout: 15000 });
  await page.waitForTimeout(2000);

  const state = () => page.evaluate(() => {
    const f = document.querySelector('[data-admin-form="attendance"]');
    const inp = f.querySelector('[data-person-search-input="student"]');
    const chip = f.querySelector('[data-person-selected="student"]');
    return {
      personType: f.dataset.personType,
      inputHidden: inp ? inp.classList.contains('hidden') : null,
      chipHidden: chip ? chip.classList.contains('hidden') : null,
      hiddenId: f.querySelector('[data-person-id="student"]')?.value,
      courseId: f.querySelector('[data-person-id="course"]')?.value,
      button: f.querySelector('[type="submit"]').textContent.trim(),
      formStatus: f.querySelector('[data-form-status]')?.textContent?.trim()
    };
  });

  out.initial = await state();

  const pick = async (kind, query) => {
    const input = page.locator(`[data-person-search-input="${kind}"]`);
    if (await input.evaluate((el) => el.classList.contains('hidden'))) {
      await page.locator(`[data-person-change="${kind}"]`).click();
      await page.waitForTimeout(300);
    }
    await input.click();
    await input.fill(query);
    await page.waitForTimeout(1000);
    await page.locator(`[data-person-search-results="${kind}"] li[role="option"]`).first().click();
    await page.waitForTimeout(500);
  };

  await pick('student', 'QASTU0001');
  await pick('course', 'Advance Excel');
  await page.locator('[data-admin-form="attendance"] input[name="date"]').fill('2026-10-01');
  await page.waitForTimeout(1000);
  out.step1_createMode = await state();

  await page.locator('[data-admin-form="attendance"] [name="status"]').selectOption('present');
  await page.locator('[data-admin-form="attendance"] [type="submit"]').click();
  await page.waitForTimeout(2500);
  out.step2_afterCreate = await state();

  await pick('student', 'QASTU0001');
  await pick('course', 'Advance Excel');
  await page.locator('[data-admin-form="attendance"] input[name="date"]').fill('2026-10-01');
  await page.waitForTimeout(1200);
  out.step3_existingDetected = await state();

  await page.locator('[data-admin-form="attendance"] [name="status"]').selectOption('absent');
  await page.locator('[data-admin-form="attendance"] [type="submit"]').click();
  await page.waitForTimeout(2500);
  out.step4_afterUpdate = await state();

  await page.locator('[data-person-type-option][value="employee"]').check();
  await page.waitForTimeout(400);
  await pick('employee', 'QAEMP0001');
  await page.locator('[data-admin-form="attendance"] input[name="date"]').fill('2026-10-01');
  await page.waitForTimeout(1200);
  out.step5_employeeCreate = await state();

  await page.locator('[data-admin-form="attendance"] [type="submit"]').click();
  await page.waitForTimeout(2500);
  out.step6_employeeSaved = await state();

  await pick('employee', 'QAEMP0001');
  await page.locator('[data-admin-form="attendance"] input[name="date"]').fill('2026-10-01');
  await page.waitForTimeout(1200);
  out.step7_employeeExisting = await state();

  out.dbCheck = await page.evaluate(async () => {
    const s = await (await fetch('/api/admin/attendance?person_type=student')).json();
    const e = await (await fetch('/api/admin/attendance?person_type=employee')).json();
    return {
      studentRows: s.attendance.map((r) => `${r.student_id}|${r.attendance_date}|${r.status}`),
      employeeRows: e.attendance.map((r) => `${r.employee_id}|${r.attendance_date}|${r.status}`)
    };
  });

  return out;
}