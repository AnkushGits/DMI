export default async function run(page, ui) {
  const out = {};
  await page.evaluate(async () => {
    await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        identifier: "QAADMIN01",
        password: "QaVerify123",
        role: "admin",
      }),
    });
  });
  await page.goto("http://127.0.0.1:5000/admin/dashboard");
  await page.waitForSelector('[data-admin-form="attendance"]', {
    timeout: 15000,
  });
  await page.waitForTimeout(2000);

  out.courses = await page.evaluate(async () => {
    const res = await fetch("/api/admin/search/courses?q=");
    const body = await res.json();
    return {
      status: res.status,
      count: body.courses?.length,
      sample: body.courses?.slice(0, 3),
    };
  });

  await page.locator('[data-person-search-input="course"]').click();
  await page.locator('[data-person-search-input="course"]').fill("Web");
  await page.waitForTimeout(1500);
  out.courseSearchState = await page.evaluate(() => {
    const list = document.querySelector(
      '[data-person-search-results="course"]',
    );
    return {
      hidden: list?.classList.contains("hidden"),
      html: list?.innerHTML?.slice(0, 300),
      count: list?.querySelectorAll("li").length,
    };
  });

  return out;
}
