# Email-AI QA/UAT Fix Pass

This build applies the requested QA fixes without changing the provider/UI architecture.

## Fixed
- Google OAuth refresh now parses token expiry, refreshes server-side, and persists rotated access token/expiry back to encrypted Neon OAuth storage.
- Existing Google refresh token is preserved if a later OAuth response omits it.
- Gmail metadata now includes To/Cc and verified authenticated account identity for recipient ownership.
- CC-only messages no longer automatically create reply/action ownership unless the authenticated user is explicitly addressed by verified name.
- Reply generation receives verified authenticated user name/email and is instructed never to borrow another participant's identity/signature.
- Exposed API keys/secrets are detected deterministically and surfaced as a high security/sensitivity risk without echoing the secret.
- Priority values are calibrated away from routine 0%/100% extremes while preserving high security/action significance.
- Business/recruiting messages are prevented from being labeled as personal relationship/sender context when the semantic bucket is professional.
- Passed/completed meeting reminders are automatically closed after the event/grace period; non-meeting deadlines can still become missed.
- Opening/deep-analyzing an email no longer silently moves it out of the currently selected inbox filter; routing changes apply on explicit refresh.
- Deep analysis exposes deterministic risk signals/reasons/URLs alongside semantic analysis.
- UI density reduced: redundant chips removed and secondary actions moved under “More actions”.

## Preserved
- Gmail Primary + Spam retrieval model
- Communication Brain architecture
- Calendar-aware scheduling chronology
- Attachment intelligence
- Multi-user workspace isolation
- Existing Neon integration store
- Existing reply/multi-reply/follow-up functionality
- Yahoo OAuth behavior

## Validation performed
- Python backend compilation (`python -m compileall`) passed.
- Deterministic exposed-secret test returns risk 0.90 and `exposed_secret` signal.
- Frontend source was updated conservatively. Full Vite build was not executable in the isolated build environment because frontend dependencies were not installed there; run `npm ci && npm run build` in the normal development/deployment environment.
