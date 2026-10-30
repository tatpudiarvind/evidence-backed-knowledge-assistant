import { expect, test } from "@playwright/test";

type ViolationLog = { cspViolations: string[] };

test("nginx sends security headers, and the app needs no exceptions to its policy", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const violations: string[] = [];
    Object.defineProperty(window, "cspViolations", { value: violations });
    document.addEventListener("securitypolicyviolation", (event) => {
      violations.push(`${event.effectiveDirective}: ${event.blockedURI}`);
    });
  });

  const response = await page.goto("/");
  if (response === null) {
    throw new Error("Opening the app returned no response.");
  }
  const headers = response.headers();
  expect(headers["content-security-policy"]).toContain("default-src 'self'");
  expect(headers["content-security-policy"]).toContain("frame-ancestors 'none'");
  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(headers["x-frame-options"]).toBe("DENY");
  expect(headers["referrer-policy"]).toBe("no-referrer");

  // The API's own responses pass through nginx, which adds the same headers once.
  const api = await page.request.get("/health/ready");
  expect(api.status()).toBe(200);
  expect(api.headers()["x-content-type-options"]).toBe("nosniff");
  expect(api.headers()["content-security-policy"]).toContain("default-src 'self'");

  await expect(page.locator(".service-status").getByRole("status")).toHaveText(
    "API and database are ready",
  );
  const violations = await page.evaluate(
    () => (window as unknown as ViolationLog).cspViolations,
  );
  expect(violations).toEqual([]);
});
