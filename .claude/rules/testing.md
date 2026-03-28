# Testing

Always use `bin/test <path>` for running individual test files. Never invoke
`.venv/bin/python3 -m pytest` or `python3 -m pytest` directly — `bin/test`
includes project-specific configuration that direct pytest invocation misses.