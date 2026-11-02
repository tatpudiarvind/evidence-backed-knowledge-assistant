import { type Page, expect, test } from "@playwright/test";

// Signs in through a real Keycloak server, in a real browser. CI starts one beside the
// production-style stack (e2e/compose.keycloak.yaml) and sets E2E_OIDC; everywhere else these
// tests are skipped. The realm's users are in e2e/keycloak/realm.json.
test.skip(!process.env.E2E_OIDC, "Needs the Keycloak stack from e2e/compose.keycloak.yaml");

const PASSWORD = "ci-only-password";

async function signInAtKeycloak(page: Page, username: string) {
  await page.goto("/");
  await page.getByRole("link", { name: "Sign in with Keycloak" }).click();
  await page.locator("#username").fill(username);
  await page.locator("#password").fill(PASSWORD);
  await page.locator("#kc-login").click();
}

test("a new user signs in through Keycloak, and stays signed in", async ({ page }) => {
  await signInAtKeycloak(page, "verified-user");
  // The session cookie is SameSite=Strict. It was set on the redirect back from another site,
  // and the page's own requests to the API must still carry it.
  await expect(
    page.getByRole("heading", { level: 1, name: "Create your first workspace" }),
  ).toBeVisible();
  expect(new URL(page.url()).pathname).toBe("/");
  expect(page.url()).not.toContain("sign_in_error");

  await page.reload();
  await expect(
    page.getByRole("heading", { level: 1, name: "Create your first workspace" }),
  ).toBeVisible();

  const cookies = await page.context().cookies();
  const session = cookies.find((cookie) => cookie.name === "eka_session");
  expect(session?.httpOnly).toBe(true);
  expect(session?.sameSite).toBe("Strict");
  // The login cookie is gone from the page's reach, and the provider's tokens never arrive.
  expect(cookies.some((cookie) => cookie.name === "eka_oidc_login")).toBe(false);
});

test("the same user signing in again gets the same account", async ({ page }) => {
  await signInAtKeycloak(page, "verified-user");
  await expect(
    page.getByRole("heading", { level: 1, name: "Create your first workspace" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { level: 2, name: "Sign in", exact: true })).toBeVisible();

  const me = await page.request.get("/api/v1/auth/me");
  expect(me.status()).toBe(401);

  // Keycloak still has its own session, so it signs the user in without asking again.
  await page.getByRole("link", { name: "Sign in with Keycloak" }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Create your first workspace" }),
  ).toBeVisible();
  const signedIn = await page.request.get("/api/v1/auth/me");
  expect(signedIn.status()).toBe(200);
  expect(((await signedIn.json()) as { email: string }).email).toBe("verified-user@example.com");
});

test("an email the provider hasn't verified is refused", async ({ page }) => {
  await signInAtKeycloak(page, "unverified-user");
  await expect(page.getByRole("alert")).toContainText("hasn't verified your email address");
  expect((await page.request.get("/api/v1/auth/me")).status()).toBe(401);
});

test("an email that already has a password account is refused", async ({ page }) => {
  const registered = await page.request.post("/api/v1/auth/register", {
    headers: { "X-CSRF-Protection": "1" },
    data: { email: "taken-user@example.com", password: "end-to-end test password" },
  });
  expect(registered.status()).toBe(201);
  await page.request.post("/api/v1/auth/logout", { headers: { "X-CSRF-Protection": "1" } });

  await signInAtKeycloak(page, "taken-user");
  await expect(page.getByRole("alert")).toContainText("already exists");
  expect((await page.request.get("/api/v1/auth/me")).status()).toBe(401);
});
