# Yahoo OAuth-only integration

This patch intentionally adds Yahoo only. Existing Gmail, inbox intelligence, calendar,
attachments, reminders, reply logic, database wiring, and Google OAuth behavior are not
redesigned.

## Render environment variables

YAHOO_CLIENT_ID=<Yahoo Developer app Client ID>
YAHOO_CLIENT_SECRET=<Yahoo Developer app Client Secret>
YAHOO_REDIRECT_URI=https://<your-render-service>/integrations/yahoo/callback
FRONTEND_URL=https://email-risk-ai-enterprise.vercel.app

Register the same HTTPS callback URL in the Yahoo Developer application.

## Yahoo permissions

The OAuth request uses:

- openid
- profile
- email
- mail-r

Yahoo documents `mail-r` as the Mail API read scope and also documents mail as a
restricted scope. Your Yahoo Developer application must be approved/enabled for the
restricted Mail permission.

## Important: no IMAP fallback

This build does not use Yahoo IMAP and does not ask users for Yahoo app passwords.

Because Yahoo's public OAuth documentation does not publish a general mailbox REST
endpoint contract that can be safely assumed for an unapproved application, this patch
does not invent one. Until Yahoo enables Mail API access for your developer app, selecting
Yahoo and loading the inbox returns a clear service error rather than falling back to IMAP.

Once Yahoo grants Mail API access and provides/activates the mailbox API contract for your
application, the provider adapter can be connected to the existing normalized inbox
pipeline without changing Gmail.
