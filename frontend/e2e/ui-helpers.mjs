// Shared UI steps for the browser checks. Demo scenarios live in the "Try a scenario" menu and
// account/demo actions in the account menu (UI redesign), so each check opens the menu first.
export async function runScenario(page, key) {
  await page.getByTestId("scenario-menu").click();
  await page.getByTestId(`scenario-${key}`).click();
}
export async function openAccountMenu(page) {
  await page.getByTestId("account-menu").click();
  await page.getByTestId("account-panel").waitFor();
}
