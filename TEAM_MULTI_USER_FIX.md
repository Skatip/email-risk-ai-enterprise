# Team Multi-User Testing Fix

This patch fixes browser/account crossover during Google OAuth team testing without changing the inbox analysis pipeline.

## Changes
- Every new Google connection starts with a fresh opaque workspace/user id.
- Google OAuth callback returns that exact id; the frontend stores it as the active account context.
- Google account chooser is explicitly shown during connection/switching.
- Added **Switch account** in the inbox header. It disconnects the current workspace, clears account-scoped UI state, and starts a fresh OAuth flow.
- A reused workspace id can have only one active Google account in the integration store.
- Manual importance/less/spam/promo feedback now includes `user_id` and is stored per user so teammate corrections do not train another teammate's preferences.
- The legacy analysis workflow now forwards `user_id` when fetching Gmail and recording analytics.

## Important
This is suitable for controlled OAuth test-user/team testing. The opaque `user_id` is still a browser-held bearer identifier, not a complete production authentication/session system. Before opening the service to the public, replace it with a server-authenticated session/JWT model and authorization middleware.
