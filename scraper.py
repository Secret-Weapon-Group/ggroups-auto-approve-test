"""Google Groups scraper using Playwright browser automation."""

import asyncio
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

import config

log = logging.getLogger("scraper")

DEBUG_DIR = config.BASE_DIR / "debug"


@dataclass
class PendingMessage:
    """A pending message from Google Groups."""
    id: str  # unique identifier for this message (index-based)
    sender: str
    subject: str
    snippet: str  # short preview text
    body: str  # full message body
    date: str
    status: str = "ok"  # "ok" or "hold"
    ai_recommendation: str = ""  # "approve" or "hold"
    ai_reason: str = ""
    ai_summary: str = ""  # summary for long messages


class GoogleGroupsScraper:
    """Scrapes and moderates pending messages from Google Groups."""

    def __init__(self, group_url: str = None, headless: bool = True, fresh_profile: bool = False, debug: bool = False):
        self.group_url = (group_url or config.GROUP_URL).rstrip("/")
        self.headless = headless
        self.fresh_profile = fresh_profile
        self.debug = debug
        self._playwright = None
        self._browser: Browser = None
        self._context: BrowserContext = None
        self._page: Page = None
        self._cached_msg_selector: str | None = None  # Cache the working selector
        self._cached_body_selector: str | None = None
        if self.debug:
            DEBUG_DIR.mkdir(exist_ok=True)

    async def _dbg(self, label: str, save_screenshot: bool = True):
        """Log debug info: URL, page title, and optionally a screenshot."""
        if not self.debug:
            return
        url = self._page.url
        title = await self._page.title()
        log.debug(f"[{label}] url={url} title={title}")
        if save_screenshot:
            ts = datetime.now().strftime("%H%M%S_%f")[:-3]
            safe_label = label.replace(" ", "_").replace("/", "_")[:40]
            path = DEBUG_DIR / f"{ts}_{safe_label}.png"
            await self._page.screenshot(path=str(path), full_page=False)
            log.debug(f"[{label}] screenshot: {path}")

    async def start(self):
        """Start the browser."""
        if self.fresh_profile and config.BROWSER_PROFILE_DIR.exists():
            shutil.rmtree(config.BROWSER_PROFILE_DIR)
            config.BROWSER_PROFILE_DIR.mkdir(exist_ok=True)

        self._playwright = await async_playwright().start()
        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(config.BROWSER_PROFILE_DIR),
            headless=self.headless,
            viewport={"width": 1280, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()

    async def stop(self):
        """Close the browser."""
        if self._context:
            await self._context.close()
        if self._playwright:
            await self._playwright.stop()

    async def ensure_logged_in(self) -> bool:
        """Check if we're logged in, return True if yes.
        If not logged in and running headless, returns False (caller should re-run with headless=False).
        If not logged in and running visible, waits for user to complete login.
        """
        await self._page.goto(self.group_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(1)

        # Check if we're on a login page
        url = self._page.url
        if "accounts.google.com" in url or "signin" in url.lower():
            if self.headless:
                return False  # Need to re-run in visible mode

            # Visible mode: wait for user to complete login
            print("\n>>> Please log in to your Google account in the browser window.")
            print(">>> Waiting for login to complete...\n")

            # Wait until we're back on groups.google.com (up to 5 minutes)
            try:
                await self._page.wait_for_url(
                    "**/groups.google.com/**",
                    timeout=300000,
                )
                await asyncio.sleep(1)
                print(">>> Login successful!\n")
                return True
            except Exception:
                print(">>> Login timed out.")
                return False

        return True

    async def fetch_pending_messages(self) -> list[PendingMessage]:
        """Navigate to pending messages and extract them."""
        pending_url = f"{self.group_url}/pending-messages"
        await self._page.goto(pending_url, wait_until="domcontentloaded", timeout=30000)

        messages = []

        # Google Groups renders pending messages as a list of conversation items.
        # Wait for the SPA to render content (wait for any message element to appear)
        message_elements = await self._find_message_elements()

        if not message_elements:
            # Check if there's a "no pending messages" indicator
            page_text = await self._page.inner_text("body")
            if "no pending" in page_text.lower() or "empty" in page_text.lower():
                return []
            # If we can't find messages, try to get whatever is on the page
            return []

        for i, elem in enumerate(message_elements):
            msg = await self._extract_message_from_element(elem, str(i))
            if msg:
                messages.append(msg)

        return messages

    async def _find_message_elements(self):
        """Find message elements on the pending messages page.

        Uses a cached selector when available to avoid slow sequential probing.
        """
        selectors = [
            '[role="listitem"]',
            ".aDP",
            ".ao3",
            'div[data-topic-id]',
            "tr[data-legacy-topic-id]",
            'div[jscontroller] > div[role="row"]',
            'div[data-id]',
            '[role="row"]',
        ]

        await self._dbg("find_msg_elements", save_screenshot=False)

        # Fast path: use cached selector
        if self._cached_msg_selector:
            try:
                await self._page.wait_for_selector(self._cached_msg_selector, timeout=5000)
                elements = await self._page.query_selector_all(self._cached_msg_selector)
                if elements:
                    return elements
            except Exception:
                self._cached_msg_selector = None  # Cache invalidated

        # First time: wait for SPA to render using a combined selector,
        # then figure out which specific one matched.
        combined = ", ".join(selectors)
        try:
            await self._page.wait_for_selector(combined, timeout=10000)
        except Exception:
            return []

        # Now quickly check which selector gives us elements (no waiting needed)
        for selector in selectors:
            try:
                elements = await self._page.query_selector_all(selector)
                if elements:
                    self._cached_msg_selector = selector
                    log.debug(f"msg selector: '{selector}' -> {len(elements)} elements")
                    return elements
            except Exception:
                continue

        return []

    async def _extract_message_from_element(self, elem, msg_id: str) -> PendingMessage | None:
        """Extract message details from a DOM element."""
        try:
            text = await elem.inner_text()
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            if not lines:
                return None

            # Try to parse the text into fields.
            # Google Groups typically shows: sender, subject, snippet, date
            sender = lines[0] if len(lines) > 0 else "Unknown"
            subject = lines[1] if len(lines) > 1 else "(no subject)"
            snippet = lines[2] if len(lines) > 2 else ""
            date = lines[-1] if len(lines) > 3 else ""

            return PendingMessage(
                id=msg_id,
                sender=sender,
                subject=subject,
                snippet=snippet,
                body="",  # Will be populated by clicking into the message
                date=date,
            )
        except Exception:
            return None

    async def _extract_expanded_body(self, element) -> str:
        """Extract the message body from an expanded message row.

        Google Groups pending page expands messages in-place when clicked.
        The expanded area contains the full message body below the summary line.
        """
        try:
            # The expanded element's inner text contains everything:
            # sender, subject, body, footer. We want just the body portion.
            text = await element.inner_text()
            lines = list(text.split("\n"))

            # The first few lines are metadata (sender, subject, date).
            # The body starts after those. We already have sender/subject
            # from the list parse, so look for the body content after them.
            # Skip short metadata lines at the top.
            if len(lines) <= 3:
                return text.strip()

            # Return everything — the trim_for_analysis in analyzer.py
            # will strip headers/footers for AI, and the TUI shows the full body
            return text.strip()
        except Exception:
            return ""

    async def fetch_all_message_bodies(self, messages: list[PendingMessage], on_progress=None):
        """Fetch bodies for all messages by clicking to expand each one.

        Google Groups pending messages page expands messages in-place (no navigation).
        We click each row, extract the expanded body, then press Escape to collapse.

        on_progress(i, total, msg) is called after each message is fetched.
        """
        if not messages:
            return

        total = len(messages)
        await self._dbg("fetch_bodies_start")

        for i, msg in enumerate(messages):
            try:
                elements = await self._find_message_elements()
                idx = int(msg.id)
                if idx >= len(elements):
                    log.debug(f"[msg {i}] idx {idx} >= {len(elements)} elements, skipping")
                    continue

                log.debug(f"[msg {i}] clicking '{msg.subject}'")
                await elements[idx].click()
                await asyncio.sleep(1)  # Wait for expansion animation

                await self._dbg(f"msg{i}_expanded")

                # Extract body from the expanded element
                # After clicking, the element expands to show the full message.
                # Re-query the element since DOM changed.
                elements = await self._find_message_elements()
                if idx < len(elements):
                    body = await self._extract_expanded_body(elements[idx])
                    if body:
                        msg.body = body
                        log.debug(f"[msg {i}] body from expansion ({len(body)} chars)")
                    else:
                        msg.body = msg.snippet or "(could not extract body)"
                        log.debug(f"[msg {i}] expansion empty, using snippet")
                else:
                    msg.body = msg.snippet or "(could not extract body)"

                # Collapse by pressing Escape
                await self._page.keyboard.press("Escape")
                await asyncio.sleep(0.3)

                if on_progress:
                    on_progress(i + 1, total, msg)

            except Exception as e:
                log.debug(f"[msg {i}] exception: {e}")
                await self._dbg(f"msg{i}_error")
                msg.body = f"(Could not fetch body: {e})"
                # Try pressing Escape to recover
                try:
                    await self._page.keyboard.press("Escape")
                    await asyncio.sleep(0.3)
                except Exception:
                    pass

    async def _dump_row_elements(self, elem, msg_id: str):
        """Debug helper: dump all interactive elements in a row via JS."""
        if not self.debug:
            return
        try:
            info = await self._page.evaluate('''(el) => {
                const results = [];
                // Broad search: any element that might be clickable
                const all = el.querySelectorAll('button, [role="button"], [jsaction], [data-tooltip], [aria-label], svg, [class*="icon"], [class*="btn"]');
                for (const c of all) {
                    results.push({
                        tag: c.tagName,
                        text: (c.textContent || '').trim().substring(0, 80),
                        ariaLabel: c.getAttribute('aria-label') || '',
                        tooltip: c.getAttribute('data-tooltip') || '',
                        jsaction: (c.getAttribute('jsaction') || '').substring(0, 120),
                        role: c.getAttribute('role') || '',
                        classes: c.className || '',
                        id: c.id || '',
                    });
                }
                return results;
            }''', elem)
            for item in info:
                log.debug(f"[row {msg_id}] {item['tag']} text='{item['text']}' "
                          f"aria='{item['ariaLabel']}' tooltip='{item['tooltip']}' "
                          f"jsaction='{item['jsaction']}' role='{item['role']}' "
                          f"class='{item['classes']}' id='{item['id']}'")
        except Exception as e:
            log.debug(f"[row {msg_id}] dump failed: {e}")

    async def _find_approve_button(self, elem, msg_id: str):
        """Find the approve (checkmark) button in a message row.

        Tries multiple strategies:
        1. aria-label / data-tooltip selectors
        2. Material icon text matching (check_circle, done, etc.)
        3. JS-based search for any clickable with approve-like attributes
        4. Positional: the first of two action icons on the right side
        """
        # Strategy 1: Direct CSS selectors
        selectors = [
            '[aria-label*="Approve" i]',
            '[data-tooltip*="Approve" i]',
            '[aria-label*="Accept" i]',
            '[data-tooltip*="Accept" i]',
            '[aria-label*="approve" i]',
        ]
        for sel in selectors:
            btn = await elem.query_selector(sel)
            if btn:
                log.debug(f"[approve {msg_id}] found via CSS '{sel}'")
                return btn

        # Strategy 2: Use JavaScript to find by text content, attributes, or icon classes
        # Google Groups uses material icons — the approve icon might have text like
        # "check_circle", "done", "check", "task_alt", or similar
        handle = await self._page.evaluate_handle('''(el) => {
            const approveKeywords = ['check_circle', 'check', 'done', 'task_alt',
                                      'approve', 'accept', 'verified'];
            const rejectKeywords = ['cancel', 'close', 'block', 'remove', 'reject',
                                     'delete', 'clear'];

            // Search all elements that might be clickable
            const candidates = el.querySelectorAll(
                'button, [role="button"], [jsaction], [data-tooltip], [aria-label]'
            );

            for (const c of candidates) {
                const text = (c.textContent || '').trim().toLowerCase();
                const label = (c.getAttribute('aria-label') || '').toLowerCase();
                const tooltip = (c.getAttribute('data-tooltip') || '').toLowerCase();
                const combined = text + ' ' + label + ' ' + tooltip;

                // Skip if it matches reject keywords
                if (rejectKeywords.some(kw => combined.includes(kw))) continue;

                // Match approve keywords
                if (approveKeywords.some(kw => combined.includes(kw))) {
                    return c;
                }
            }

            // Strategy 3: Positional — find the two rightmost action icons.
            // In Google Groups pending page, each row has ✓ then ✗ icons.
            // Find elements that look like icon buttons (small, near right edge).
            const allClickable = el.querySelectorAll(
                'button, [role="button"], [jsaction]'
            );
            const actionBtns = [];
            for (const c of allClickable) {
                // Skip elements that are likely checkboxes or the main row itself
                const rect = c.getBoundingClientRect();
                if (rect.width > 0 && rect.width < 60 && rect.height > 0 && rect.height < 60) {
                    actionBtns.push(c);
                }
            }

            // If we found exactly 2 small action buttons, the first is approve
            if (actionBtns.length >= 2) {
                // Return the second-to-last (approve comes before reject)
                return actionBtns[actionBtns.length - 2];
            }

            return null;
        }''', elem)

        # Convert JSHandle to ElementHandle
        btn = handle.as_element()
        if btn:
            # Log what we found
            if self.debug:
                info = await self._page.evaluate('''(el) => ({
                    tag: el.tagName,
                    text: (el.textContent || '').trim().substring(0, 50),
                    ariaLabel: el.getAttribute('aria-label') || '',
                    tooltip: el.getAttribute('data-tooltip') || '',
                })''', btn)
                log.debug(f"[approve {msg_id}] found via JS: {info}")
            return btn

        log.debug(f"[approve {msg_id}] no approve button found by any strategy")
        return None

    async def _handle_approve_confirm(self) -> bool:
        """Handle the 'Approve message?' confirmation dialog.

        Google Groups shows a Material Design dialog with Cancel/OK buttons.
        These are NOT <button> elements — they're typically <div role="button">
        or similar, so we use broad selectors and JS fallback.
        """
        await asyncio.sleep(0.5)  # Let dialog render
        await self._dbg("approve_confirm_dialog")

        # Strategy 1: Playwright text-based locator (matches any element with text)
        try:
            ok_locator = self._page.get_by_role("button", name="OK")
            if await ok_locator.count() > 0:
                await ok_locator.click()
                log.debug("[approve] clicked OK via role=button name=OK")
                await asyncio.sleep(1)
                return True
        except Exception as e:
            log.debug(f"[approve] role-button OK failed: {e}")

        # Strategy 2: Broad CSS selectors for any clickable "OK" element
        ok_selectors = [
            'button:has-text("OK")',
            '[role="button"]:has-text("OK")',
            '[data-mdc-dialog-action="ok"]',
            '[data-mdc-dialog-action="accept"]',
            '.mdc-dialog__button--accept',
        ]
        for sel in ok_selectors:
            try:
                elem = await self._page.wait_for_selector(sel, timeout=1000)
                if elem:
                    await elem.click()
                    log.debug(f"[approve] clicked OK via '{sel}'")
                    await asyncio.sleep(1)
                    return True
            except Exception:
                continue

        # Strategy 3: JavaScript — find any element containing exactly "OK" text
        # in a dialog/overlay context
        try:
            clicked = await self._page.evaluate('''() => {
                // Look for dialog/overlay elements
                const dialogs = document.querySelectorAll(
                    '[role="dialog"], [role="alertdialog"], .mdc-dialog, [class*="dialog"], [class*="modal"]'
                );
                for (const dialog of dialogs) {
                    // Find clickable elements with "OK" text inside the dialog
                    const clickables = dialog.querySelectorAll(
                        'button, [role="button"], [jsaction*="click"], a, [tabindex]'
                    );
                    for (const el of clickables) {
                        const text = (el.textContent || '').trim();
                        if (text === 'OK' || text === 'Ok' || text === 'Approve') {
                            el.click();
                            return 'clicked: ' + text;
                        }
                    }
                }
                // Broader fallback: any element on the page with text "OK" that looks clickable
                const all = document.querySelectorAll(
                    'button, [role="button"], [jsaction*="click"]'
                );
                for (const el of all) {
                    const text = (el.textContent || '').trim();
                    if (text === 'OK') {
                        el.click();
                        return 'clicked-fallback: ' + text;
                    }
                }
                return null;
            }''')
            if clicked:
                log.debug(f"[approve] JS {clicked}")
                await asyncio.sleep(1)
                return True
        except Exception as e:
            log.debug(f"[approve] JS confirm click failed: {e}")

        log.debug("[approve] could not find/click confirmation button")
        await self._dbg("approve_confirm_failed")
        return False

    async def approve_messages(self, message_ids: list[str]) -> dict[str, bool]:
        """Approve the specified pending messages by clicking per-row approve buttons.

        Google Groups pending page has ✓ (approve) and ✗ (reject) icons on each row.
        We click the ✓ button for each message to approve, then verify it was removed.

        Returns a dict of {msg_id: success_bool}.
        """
        results = {}
        if not message_ids:
            return results

        try:
            pending_url = f"{self.group_url}/pending-messages"
            await self._page.goto(pending_url, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(1)
            await self._dbg("approve_start")

            # Dump first row's elements in debug mode to discover correct selectors
            if self.debug:
                elements = await self._find_message_elements()
                if elements:
                    await self._dump_row_elements(elements[0], "0")

            # Process in reverse index order so indices stay valid as rows are removed
            for msg_id in sorted(message_ids, key=int, reverse=True):
                try:
                    elements = await self._find_message_elements()
                    idx = int(msg_id)

                    if idx >= len(elements):
                        log.debug(f"[approve {msg_id}] idx {idx} >= {len(elements)}, skipping")
                        results[msg_id] = False
                        continue

                    count_before = len(elements)
                    elem = elements[idx]

                    approve_btn = await self._find_approve_button(elem, msg_id)

                    if approve_btn:
                        await self._dbg(f"approve_{msg_id}_before_click")
                        await approve_btn.click()
                        await asyncio.sleep(1)
                        await self._dbg(f"approve_{msg_id}_after_click")

                        # Handle confirmation dialog if present
                        await self._handle_approve_confirm()

                        # Verify: check if row count decreased (message was actually approved)
                        await asyncio.sleep(1)
                        elements_after = await self._find_message_elements()
                        count_after = len(elements_after) if elements_after else 0

                        if count_after < count_before:
                            results[msg_id] = True
                            log.debug(f"[approve {msg_id}] VERIFIED: {count_before} -> {count_after} rows")
                        else:
                            # Row count didn't change — approval didn't work
                            log.debug(f"[approve {msg_id}] NOT verified: still {count_after} rows")
                            await self._dbg(f"approve_{msg_id}_not_verified")
                            results[msg_id] = False
                    else:
                        await self._dbg(f"approve_{msg_id}_no_btn")
                        results[msg_id] = False

                except Exception as e:
                    log.debug(f"[approve {msg_id}] error: {e}")
                    await self._dbg(f"approve_{msg_id}_error")
                    results[msg_id] = False

        except Exception as e:
            log.debug(f"[approve] top-level error: {e}")
            print(f"Error approving messages: {e}")

        return results

    async def fetch_group_description(self) -> str:
        """Fetch the group's About page for rules/description."""
        try:
            about_url = f"{self.group_url}/about"
            await self._page.goto(about_url, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(1)

            # Try to extract description text
            desc_selectors = [
                '[role="article"]',
                ".group-description",
                "main",
                '[role="main"]',
            ]

            for selector in desc_selectors:
                try:
                    elem = await self._page.wait_for_selector(selector, timeout=3000)
                    if elem:
                        text = await elem.inner_text()
                        if text.strip():
                            return text.strip()
                except Exception:
                    continue

            return ""
        except Exception:
            return ""


async def login_flow():
    """Run the manual login flow in a visible browser."""
    scraper = GoogleGroupsScraper(headless=False)
    await scraper.start()
    try:
        logged_in = await scraper.ensure_logged_in()
        if logged_in:
            print("Session saved. You can now run in headless mode.")
        else:
            print("Login was not completed.")
    finally:
        await scraper.stop()


async def fetch_all_pending() -> list[PendingMessage]:
    """Fetch all pending messages (with bodies) from the group."""
    scraper = GoogleGroupsScraper(headless=True)
    await scraper.start()
    try:
        logged_in = await scraper.ensure_logged_in()
        if not logged_in:
            print("Not logged in. Run with --login first.")
            return []

        messages = await scraper.fetch_pending_messages()

        # Fetch bodies for all messages
        for msg in messages:
            if not msg.body:
                await scraper.fetch_message_body(msg)

        return messages
    finally:
        await scraper.stop()
