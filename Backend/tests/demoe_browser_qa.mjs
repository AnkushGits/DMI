export default async function run(page) {
  await page.getByRole("button", { name: "Open DEMOE AI Assistant" }).click();
  await page
    .getByRole("button", { name: "What are my benefits by joining it?" })
    .waitFor();
  const count = await page.locator(".demoe-faqs button").count();
  await page
    .getByRole("button", { name: "What are my benefits by joining it?" })
    .click();
  await page.getByText("DEMOE is typing...").waitFor({ state: "hidden" });
  const answer = await page.locator(".demoe-message").last().innerText();
  await page
    .getByRole("textbox", { name: "Type your question" })
    .fill("What is Tally?");
  await page.getByRole("button", { name: "Send message" }).click();
  await page.getByText("DEMOE is typing...").waitFor({ state: "hidden" });
  const ai = await page.locator(".demoe-message").last().innerText();
  await page.getByRole("button", { name: "Close DEMOE" }).click();
  const closed = await page.locator(".demoe-panel").getAttribute("aria-hidden");
  await page.getByRole("button", { name: "Open DEMOE AI Assistant" }).click();
  const reopened = await page
    .locator(".demoe-panel")
    .getAttribute("aria-hidden");
  const mobile = await page.evaluate(() => {
    const p = document.querySelector(".demoe-panel").getBoundingClientRect();
    return {
      width: innerWidth,
      left: p.left,
      right: p.right,
      height: p.height,
    };
  });
  return { count, answer, ai, closed, reopened, mobile };
}
