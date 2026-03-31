# Check Test Requirements

When adding or modifying a check in `checks/`, also add at least 2
corpus entries to `tests/email_corpus.py` (1 that triggers the check,
1 that passes through) plus boundary test cases for any thresholds.

The structural test `test_every_check_has_corpus_entries` in
`tests/test_checks.py` enforces this — CI will fail if a check
module lacks corpus coverage.