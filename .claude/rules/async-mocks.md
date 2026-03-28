# AsyncMock vs MagicMock

When mocking async objects, use `MagicMock` for the object
and only use `AsyncMock` for methods that are actually awaited.

**Do this:**
```python
monitor = MagicMock()
monitor.connect = AsyncMock()
monitor.disconnect = AsyncMock()
monitor.fetch_pending = AsyncMock(return_value=[])
monitor.approve_messages = AsyncMock(return_value={})
```

**Never make the entire object AsyncMock:**
```python
monitor = AsyncMock()  # Makes ALL child attributes async — causes coroutine leaks
```

This causes every attribute access to create async child mocks.
When synchronous methods are called without `await`, the coroutines
leak and produce `RuntimeWarning: coroutine was never awaited`.