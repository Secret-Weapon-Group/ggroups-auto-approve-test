# Testing

Always use `bin/test <path>` for running individual test files. Never invoke
`.venv/bin/python3 -m pytest` or `python3 -m pytest` directly — `bin/test`
includes project-specific configuration that direct pytest invocation misses.

When writing async tests, check existing test files for the correct
`@pytest.mark.asyncio` decorator syntax before writing new ones. Do not
add arguments to the decorator (e.g., `mode="strict"`) — use the plain
decorator that existing tests use.