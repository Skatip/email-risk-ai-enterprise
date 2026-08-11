# Hosted testing deployment

## 1. Neon PostgreSQL
Create a free Neon project, copy the pooled connection string, and set it as `DATABASE_URL` in Render.

## 2. OpenAI
Create a project API key and set `OPENAI_API_KEY` in Render. Set a small monthly project budget during testing.

## 3. Google OAuth
Create one Web OAuth client for the product. Add the Render callback URL:

`https://<render-service>.onrender.com/integrations/google/callback`

Set the client ID, client secret, callback URL, frontend URL, and a Fernet encryption key in Render. Users only click Connect Gmail; they never handle keys or token files.

## 4. Render backend
Create a Render Blueprint from `render.yaml`, or create a Python web service rooted at `backend`.

## 5. Vercel frontend
Import the repository in Vercel with root directory `frontend`. Set `VITE_API_BASE` to the Render API URL.

## 6. Supabase Storage
Optional during initial testing. Create a private bucket and set the three `SUPABASE_*` variables when persistent attachment storage is required.

## 7. Test flow
Open the Vercel URL, connect Gmail through the consent screen, sync messages, test analysis, attachment intelligence, replies, no-reply decisions, clarification questions, follow-ups, and approval-gated actions.
