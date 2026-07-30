import { test, expect, type Page } from "@playwright/test";

/**
 * The Phase 5 review pass, in a real browser.
 *
 * Every /api/** call is mocked here: the API's behaviour is covered by the
 * backend suite, and what these tests are for is the editor's own logic -
 * dirty tracking, which buttons are live when, the draft/approved badge, and
 * the shape of the PUT it sends. No key, no LLM, no database.
 */

const LISTING_ID = 1;

// 1x1 transparent PNG, so slide thumbnails resolve without real photos.
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQI12P4//8/AAX+Av7czFnnAAAAAElFTkSuQmCC",
  "base64",
);

type Slide = {
  id: number;
  listing_photo_id: number | null;
  order_index: number;
  caption: string;
  photo_url: string | null;
};

function freshPackage() {
  return {
    id: 10,
    listing_id: LISTING_ID,
    status: "draft",
    generated_at: "2026-07-29 12:00:00",
    reel_script: "Open wide on the water. Push in on the pool.",
    slides: [
      {
        id: 1,
        listing_photo_id: 7,
        order_index: 0,
        caption: "Light spills across the lanai.",
        photo_url: `/listings/${LISTING_ID}/photos/7`,
      },
      {
        id: 2,
        listing_photo_id: 8,
        order_index: 1,
        caption: "The pool holds the last of the sun.",
        photo_url: `/listings/${LISTING_ID}/photos/8`,
      },
    ] as Slide[],
    captions: [
      { id: 4, label: "Lifestyle hook", text: "Mornings here are unhurried." },
      { id: 5, label: "Just listed", text: "Newly available in Wailea." },
    ],
  };
}

type State = {
  pkg: ReturnType<typeof freshPackage>;
  puts: unknown[];
  photoRequests: number;
};

/** Sign the browser in and serve the whole API from in-memory state. */
async function mockApi(page: Page): Promise<State> {
  const state: State = { pkg: freshPackage(), puts: [], photoRequests: 0 };

  await page.addInitScript(() => {
    window.localStorage.setItem(
      "l2c.auth",
      JSON.stringify({ user: { id: 1, email: "agent@studio.com" }, token: "test-token" }),
    );
  });

  await page.route("**/api/auth/me", (route) =>
    route.fulfill({ json: { id: 1, email: "agent@studio.com" } }),
  );

  await page.route(`**/api/listings/${LISTING_ID}`, (route) =>
    route.fulfill({ json: { id: LISTING_ID, title: "Oceanfront Villa Kai", photos: [] } }),
  );

  await page.route("**/api/listings/*/photos/*", (route) => {
    state.photoRequests += 1;
    return route.fulfill({ contentType: "image/png", body: PNG });
  });

  // Registered before the /package route below; the glob for that one ends at
  // "package", so it cannot swallow this path.
  await page.route(`**/api/listings/${LISTING_ID}/package/approve`, (route) => {
    state.pkg.status = "approved";
    return route.fulfill({ json: state.pkg });
  });

  await page.route(`**/api/listings/${LISTING_ID}/package`, (route) => {
    if (route.request().method() === "PUT") {
      const body = route.request().postDataJSON();
      state.puts.push(body);
      state.pkg.reel_script = body.reel_script;
      for (const edit of body.slides) {
        const slide = state.pkg.slides.find((s) => s.id === edit.id);
        if (slide) slide.caption = edit.caption;
      }
      for (const edit of body.captions) {
        const caption = state.pkg.captions.find((c) => c.id === edit.id);
        if (caption) caption.text = edit.text;
      }
      // Saving returns an approved package to draft.
      state.pkg.status = "draft";
    }
    return route.fulfill({ json: state.pkg });
  });

  return state;
}

const slideCaption = (page: Page, n: number) =>
  page.getByLabel(`Slide ${n} caption`);
const saveButton = (page: Page) => page.getByRole("button", { name: "Save edits" });
const approveButton = (page: Page) => page.getByRole("button", { name: "Approve" });
const badge = (page: Page) => page.locator(".badge");
// The page carries two live regions - one for generation, one for the review
// pass - so this is scoped to the review bar rather than by role alone.
const reviewStatus = (page: Page) => page.locator(".review-bar [role='status']");

async function openPackage(page: Page) {
  await page.goto(`/listings/package/?id=${LISTING_ID}`);
  await expect(page.getByRole("heading", { name: "Oceanfront Villa Kai" })).toBeVisible();
}

test("opens with nothing to save and a package ready to approve", async ({ page }) => {
  await mockApi(page);
  await openPackage(page);

  await expect(badge(page)).toHaveText("Draft");
  // Nothing has been typed, so there is nothing to save - and nothing unsaved
  // standing in the way of approving.
  await expect(saveButton(page)).toBeDisabled();
  await expect(approveButton(page)).toBeEnabled();
  await expect(slideCaption(page, 1)).toHaveValue("Light spills across the lanai.");
});

test("editing enables Save, blocks Approve, and says why", async ({ page }) => {
  await mockApi(page);
  await openPackage(page);

  await slideCaption(page, 1).fill("My own words for this slide.");

  await expect(saveButton(page)).toBeEnabled();
  await expect(approveButton(page)).toBeDisabled();
  await expect(reviewStatus(page)).toContainText(
    "Unsaved edits - save before approving.",
  );
});

test("saving sends every piece of copy and stays a draft", async ({ page }) => {
  const state = await mockApi(page);
  await openPackage(page);

  await slideCaption(page, 2).fill("Edited second slide.");
  await page.getByLabel("Reel script").fill("A tighter script.");
  await saveButton(page).click();

  await expect(reviewStatus(page)).toContainText("Saved.");
  await expect(saveButton(page)).toBeDisabled();
  await expect(approveButton(page)).toBeEnabled();
  await expect(badge(page)).toHaveText("Draft");

  // One PUT carrying the whole package, keyed by row id.
  expect(state.puts).toHaveLength(1);
  expect(state.puts[0]).toEqual({
    reel_script: "A tighter script.",
    slides: [
      { id: 1, caption: "Light spills across the lanai." },
      { id: 2, caption: "Edited second slide." },
    ],
    captions: [
      { id: 4, text: "Mornings here are unhurried." },
      { id: 5, text: "Newly available in Wailea." },
    ],
  });
});

test("an edit survives a reload", async ({ page }) => {
  await mockApi(page);
  await openPackage(page);

  await slideCaption(page, 1).fill("This must still be here.");
  await saveButton(page).click();
  await expect(reviewStatus(page)).toContainText("Saved.");

  await page.reload();
  await expect(slideCaption(page, 1)).toHaveValue("This must still be here.");
});

test("approving flips the badge and closes the action", async ({ page }) => {
  await mockApi(page);
  await openPackage(page);

  await approveButton(page).click();

  await expect(badge(page)).toHaveText("Approved");
  await expect(badge(page)).toHaveClass(/badge--approved/);
  await expect(approveButton(page)).toBeDisabled();
});

test("editing an approved package returns it to draft", async ({ page }) => {
  await mockApi(page);
  await openPackage(page);

  await approveButton(page).click();
  await expect(badge(page)).toHaveText("Approved");

  await slideCaption(page, 1).fill("Changed my mind.");
  await saveButton(page).click();

  await expect(reviewStatus(page)).toContainText("Saved.");
  await expect(badge(page)).toHaveText("Draft");
});

test("typing does not refetch the slide photos", async ({ page }) => {
  const state = await mockApi(page);
  await openPackage(page);
  await expect(page.locator(".slide img").first()).toBeVisible();

  const afterLoad = state.photoRequests;
  expect(afterLoad).toBe(2);

  await slideCaption(page, 1).fill("Typing several words here.");
  await slideCaption(page, 2).fill("And more typing here too.");

  // The editor derives photo URLs from the package it mounted with, so
  // keystrokes must not invalidate them.
  expect(state.photoRequests).toBe(afterLoad);
});
