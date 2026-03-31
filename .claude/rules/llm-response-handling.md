# LLM Response Handling

When adding defensive parsing for LLM API responses that contradict the
system prompt (e.g., model wraps JSON in markdown fences despite being
told not to), add a brief comment at the call site explaining the
observed model behavior that motivates the defense.