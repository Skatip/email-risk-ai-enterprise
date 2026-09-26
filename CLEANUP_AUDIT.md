# Email-AI cleanup audit

This build keeps the existing Render + Vercel wiring and fixes the remaining semantic classification inconsistency found after QA.

## Additional fixes in this cleanup

- Family/Personal is now treated as a **relationship**, not a synonym for "personally relevant".
- The UI only shows the Family/Personal signal when semantic analysis identifies a direct human relationship and the communication is not automated.
- The Communication Brain prompt now requires positive human-to-human evidence before assigning FAMILY/PERSONAL.
- Automated/service/account/billing/security/company-to-customer messages cannot be surfaced as Family/Personal merely because they affect the user personally.
- Removed legacy consumer-email-domain trust inference from the old sender policy path. Gmail/Yahoo/Outlook domains no longer imply personal relationship/trust.
- Removed legacy platform-domain inference from sender policy. Semantic meaning remains the authority for classification.
- Deep analysis now returns the same product `bucket` taxonomy as inbox triage. This prevents semantic state from silently falling back to INFORMATIONAL after opening an email.
- Existing frontend routing protection remains: opening an email enriches analysis without silently moving the card out of the active filter until refresh.

## Existing QA fixes retained

- OAuth refresh credentials are server-side and refreshed access token/expiry are persisted.
- CC-only recipient ownership guard.
- Authenticated-user reply identity grounding.
- Exposed API-key/secret detection.
- Priority calibration.
- Work/professional classification guidance.
- Completed meeting/follow-up lifecycle handling.
- Email/analysis state is keyed by message id.
- Reply grounding and calendar chronology protections.
- Reduced UI action clutter.

## Intentional deterministic safeguards

The product does not use company-specific rules to decide semantic category. Deterministic code remains only where it is appropriate for safety/invariants, such as OAuth isolation, recipient ownership, exposed-secret patterns, risk indicators, and preventing invalid Family/Personal UI signals.

## Validation

- Python source compilation: passed.
- Static schema/semantic consistency audit: passed.
- Frontend production build could not be completed in the isolated packaging environment because the npm dependency installation did not complete; Vercel should run the normal clean install/build from `package-lock.json` during deployment.
