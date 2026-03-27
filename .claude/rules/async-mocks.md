# AsyncMock vs MagicMock for Playwright

When mocking Playwright objects, use `MagicMock` for the object
and only use `AsyncMock` for methods that are actually awaited.

**Never do this:**
```python
scraper._page = AsyncMock()  # Makes ALL child attributes async
```

This causes every attribute access to create async child mocks.
When synchronous Playwright methods like `page.get_by_role()` or
`page.url` are called without `await`, the coroutines leak and
produce `RuntimeWarning: coroutine was never awaited`.

**Do this instead:**
```python
scraper._page = AsyncMock()
# Override synchronous methods explicitly
scraper._page.get_by_role = MagicMock(return_value=ok_locator)
```

Or use `MagicMock` for the object with explicit async methods:
```python
mock_instance = MagicMock()
mock_instance.start = AsyncMock()
mock_instance.stop = AsyncMock()
mock_instance.ensure_logged_in = AsyncMock(return_value=True)
```

**Playwright synchronous methods** (not exhaustive):
- `page.get_by_role()` — returns Locator
- `page.url` — property
- `page.get_by_text()` — returns Locator
- `page.locator()` — returns Locator

**Playwright async methods** (must use AsyncMock):
- `page.goto()`
- `page.wait_for_selector()`
- `page.query_selector_all()`
- `page.evaluate()`
- `page.screenshot()`
- `page.click()`
- `context.close()`
- `playwright.stop()`
