# Semantic repair fix

This patch addresses stale inbox intelligence without adding sender/domain/keyword semantic rules.

- Bumps the persisted Communication Brain contract to `semantic-v4-unified-brain`.
- Neon remains the immediate serving source.
- Background Gmail discovery now also repairs a bounded set of persisted rows whose `analysis_version` is older than the current Brain contract.
- Only stale rows are sent back through the Unified Communication Brain; current-version rows are reused.
- Explicit Brain decisions such as `NO_REPLY`, `ACTION_ONLY`, `WAIT`, and `ASK_USER` are no longer displayed as `Check reply` merely because the frontend state is `triaged` rather than `done`.
- No Udemy/Built In/Lensa/domain/category special cases were added.

Validation:
- Python compileall: PASS.
- Backend architecture/calendar/semantic repair tests: 8 passed.
- Frontend production build: not completed in the isolated build environment because dependency installation exceeded the tool timeout. Run `npm install` and `npm run build` locally before commit.
