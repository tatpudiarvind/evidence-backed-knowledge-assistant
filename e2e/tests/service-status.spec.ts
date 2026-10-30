import { expect, test } from "@playwright/test";

const UNAVAILABLE = JSON.stringify({ status: "unavailable", database: "unavailable" });

test("the sign-in page reports unavailable services, and checks again on request", async ({
  page,
}) => {
  await page.route("**/health/ready", (route) =>
    route.fulfill({ status: 503, contentType: "application/json", body: UNAVAILABLE }),
  );
  await page.goto("/");
  const status = page.locator(".service-status").getByRole("status");
  const checkAgain = page.getByRole("button", { name: "Check again" });
  await expect(status).toHaveText("API or database is unavailable");
  await expect(checkAgain).toBeVisible();

  // The real API answers the next check, a little late so the checking state can be seen.
  await page.unroute("**/health/ready");
  await page.route("**/health/ready", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1_500));
    await route.continue();
  });
  await checkAgain.focus();
  await page.keyboard.press("Enter");
  await expect(status).toHaveText("Checking local services");
  // aria-disabled rather than disabled, so keyboard focus stays on the button.
  await expect(checkAgain).toBeFocused();
  await expect(checkAgain).toHaveAttribute("aria-disabled", "true");

  await expect(status).toHaveText("API and database are ready");
  await expect(checkAgain).toHaveCount(0);
  await expect(status).toBeFocused();
});
