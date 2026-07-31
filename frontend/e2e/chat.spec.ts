import { test, expect, type Page } from "@playwright/test";

/**
 * The Phase 6 assistant panel, in a real browser.
 *
 * Every /api/** call is mocked - the endpoint's behaviour is covered by the
 * backend suite. What these tests are for is the panel's own logic and, mainly,
 * the thing only a browser can show: that a turn which rewrites copy or fills
 * in a field actually reaches the page hosting the panel.
 */

const LISTING_ID = 1;

const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQI12P4//8/AAX+Av7czFnnAAAAAElFTkSuQmCC",
  "base64",
);

type Message = { id: number; role: string; content: string; created_at: string };

/** What one POST /chat should do to the mocked server state. */
type Turn = { reply: string; listing?: Record<string, unknown>; caption?: string };

type State = {
  listing: Record<string, unknown>;
  pkg: {
    id: number;
    listing_id: number;
    status: string;
    generated_at: string;
    reel_script: string;
    slides: {
      id: number;
      listing_photo_id: number | null;
      order_index: number;
      caption: string;
      photo_url: string | null;
    }[];
    captions: { id: number; label: string; text: string }[];
  } | null;
  messages: Message[];
  posts: unknown[];
  next: Turn;
};

function freshState(): State {
  return {
    listing: {
      id: LISTING_ID,
      title: "Oceanfront Villa Kai",
      location: "Wailea, Maui",
      beds: null,
      photos: [],
    },
    pkg: {
      id: 10,
      listing_id: LISTING_ID,
      status: "draft",
      generated_at: "2026-07-31 12:00:00",
      reel_script: "Open wide on the water.",
      slides: [
        {
          id: 1,
          listing_photo_id: 7,
          order_index: 0,
          caption: "Light spills across the lanai.",
          photo_url: `/listings/${LISTING_ID}/photos/7`,
        },
      ],
      captions: [{ id: 4, label: "Lifestyle hook", text: "Mornings here are unhurried." }],
    },
    messages: [],
    posts: [],
    next: { reply: "Done." },
  };
}

/** Sign the browser in and serve the API from in-memory state. */
async function mockApi(page: Page): Promise<State> {
  const state = freshState();

  await page.addInitScript(() => {
    window.localStorage.setItem(
      "l2c.auth",
      JSON.stringify({ user: { id: 1, email: "agent@studio.com" }, token: "test-token" }),
    );
  });

  await page.route("**/api/auth/me", (route) =>
    route.fulfill({ json: { id: 1, email: "agent@studio.com" } }),
  );

  await page.route("**/api/listings/*/photos/*", (route) =>
    route.fulfill({ contentType: "image/png", body: PNG }),
  );

  // Each glob below stops at its own path segment, so none swallows another.
  await page.route(`**/api/listings/${LISTING_ID}`, (route) =>
    route.fulfill({ json: state.listing }),
  );

  await page.route(`**/api/listings/${LISTING_ID}/package`, (route) =>
    state.pkg
      ? route.fulfill({ json: state.pkg })
      : route.fulfill({ status: 404, json: { detail: "No content package yet" } }),
  );

  await page.route(`**/api/listings/${LISTING_ID}/chat`, (route) => {
    if (route.request().method() !== "POST") {
      return route.fulfill({ json: state.messages });
    }
    const body = route.request().postDataJSON();
    state.posts.push(body);

    const turn = state.next;
    const id = state.messages.length + 1;
    state.messages.push(
      { id, role: "user", content: body.message, created_at: "now" },
      { id: id + 1, role: "assistant", content: turn.reply, created_at: "now" },
    );
    if (turn.listing) Object.assign(state.listing, turn.listing);
    if (turn.caption && state.pkg) state.pkg.captions[0].text = turn.caption;

    return route.fulfill({
      json: {
        messages: state.messages,
        listing_changed: Boolean(turn.listing),
        package_changed: Boolean(turn.caption),
      },
    });
  });

  return state;
}

const input = (page: Page) => page.getByLabel("Message the assistant");
const sendButton = (page: Page) => page.getByRole("button", { name: "Send" });
const log = (page: Page) => page.getByRole("log", { name: "Conversation" });

async function ask(page: Page, message: string) {
  await input(page).fill(message);
  await sendButton(page).click();
}

async function openPackage(page: Page) {
  await page.goto(`/listings/package/?id=${LISTING_ID}`);
  await expect(page.getByRole("heading", { name: "Oceanfront Villa Kai" })).toBeVisible();
}

async function openDetail(page: Page) {
  await page.goto(`/listings/detail/?id=${LISTING_ID}`);
  await expect(page.getByRole("heading", { name: "Oceanfront Villa Kai" })).toBeVisible();
}

test("opens empty, with nothing to send", async ({ page }) => {
  await mockApi(page);
  await openPackage(page);

  await expect(log(page)).toContainText("Nothing yet.");
  await expect(sendButton(page)).toBeDisabled();
});

test("a turn shows both sides of the conversation", async ({ page }) => {
  const state = await mockApi(page);
  state.next = { reply: "Recorded: four beds." };
  await openPackage(page);

  await ask(page, "It has four beds.");

  await expect(log(page)).toContainText("It has four beds.");
  await expect(log(page)).toContainText("Recorded: four beds.");
  expect(state.posts).toEqual([{ message: "It has four beds." }]);
  // The box clears, so the next message starts from empty.
  await expect(input(page)).toHaveValue("");
});

test("the transcript survives a reload", async ({ page }) => {
  const state = await mockApi(page);
  state.next = { reply: "Noted." };
  await openPackage(page);

  await ask(page, "Remember this.");
  await expect(log(page)).toContainText("Noted.");

  await page.reload();
  await expect(log(page)).toContainText("Remember this.");
  await expect(log(page)).toContainText("Noted.");
});

test("a rewritten caption replaces the copy in the editor", async ({ page }) => {
  /**
   * The editor owns its state from mount, so refetching the package is not
   * enough on its own - without the remount the agent would keep reading the
   * old caption while the server held the new one.
   */
  const state = await mockApi(page);
  state.next = { reply: "Tightened it.", caption: "Mornings are slow here." };
  await openPackage(page);

  const caption = page.getByLabel("Lifestyle hook");
  await expect(caption).toHaveValue("Mornings here are unhurried.");

  await ask(page, "Make that caption shorter.");

  await expect(caption).toHaveValue("Mornings are slow here.");
  await expect(page.locator(".actions [role='status']")).toContainText(
    "The assistant rewrote copy below.",
  );
});

test("a recorded spec appears in the listing form", async ({ page }) => {
  const state = await mockApi(page);
  state.next = { reply: "Four beds it is.", listing: { beds: 4 } };
  await openDetail(page);

  await expect(page.getByLabel("Beds")).toHaveValue("");

  await ask(page, "It has four beds.");

  await expect(page.getByLabel("Beds")).toHaveValue("4");
  await expect(page.locator(".actions [role='status']")).toContainText(
    "The assistant updated this listing",
  );
});

test("a turn that changes nothing leaves the page alone", async ({ page }) => {
  const state = await mockApi(page);
  state.next = { reply: "What is the asking price?" };
  await openDetail(page);

  await page.getByLabel("Location").fill("Kapalua, Maui");
  await ask(page, "Hello.");

  await expect(log(page)).toContainText("What is the asking price?");
  // Nothing was applied, so the form must not be refetched over the top of
  // what the agent is in the middle of typing.
  await expect(page.getByLabel("Location")).toHaveValue("Kapalua, Maui");
});

test("a failed turn says so and keeps the message", async ({ page }) => {
  await mockApi(page);
  await openPackage(page);
  await page.route(`**/api/listings/${LISTING_ID}/chat`, (route) =>
    route.request().method() === "POST"
      ? route.fulfill({ status: 502, json: { detail: "The assistant did not respond" } })
      : route.fulfill({ json: [] }),
  );

  await ask(page, "Rewrite the script.");

  await expect(page.locator(".form-error")).toContainText("The assistant did not respond");
  // The agent should not have to retype what they just said.
  await expect(input(page)).toHaveValue("Rewrite the script.");
});
