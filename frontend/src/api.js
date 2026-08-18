const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

async function handle(res) {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return await res.json();
}


export async function fetchInbox({ maxResults = 12, userEmail = "", provider = "gmail", query = "", userId = "", bucket = "IMPORTANT" } = {}) {
  const url =
    `${API_BASE}/inbox?max_results=${encodeURIComponent(maxResults)}` +
    `&user_email=${encodeURIComponent(userEmail)}` +
    `&provider=${encodeURIComponent(provider)}` +
    `&query=${encodeURIComponent(query)}` +
    `&bucket=${encodeURIComponent(bucket)}` +
    `&user_id=${encodeURIComponent(userId)}`;
  const res = await fetch(url);
  return await handle(res);
}

export async function analyzeEmail(payload) {
  const res = await fetch(`${API_BASE}/email/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return await handle(res);
}

export async function fetchAnalysis({ maxResults = 10, userEmail = "", provider = "gmail", query = "", userId = "" } = {}) {
  const url =
    `${API_BASE}/analyze?max_results=${encodeURIComponent(maxResults)}` +
    `&user_email=${encodeURIComponent(userEmail)}` +
    `&provider=${encodeURIComponent(provider)}` +
    `&query=${encodeURIComponent(query)}` +
    `&user_id=${encodeURIComponent(userId)}`;
  const res = await fetch(url);
  return await handle(res);
}

export async function fetchDrafts({ maxResults = 5, replyTopN = 1, userEmail = "", provider = "gmail" } = {}) {
  const url =
    `${API_BASE}/analyze?max_results=${encodeURIComponent(maxResults)}` +
    `&include_reply=true` +
    `&reply_top_n=${encodeURIComponent(replyTopN)}` +
    `&user_email=${encodeURIComponent(userEmail)}` +
    `&provider=${encodeURIComponent(provider)}`;
  const res = await fetch(url);
  return await handle(res);
}

export async function generateReply(payload) {
  const res = await fetch(`${API_BASE}/reply/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return await handle(res);
}

export async function fetchMultiReply(payload) {
  const res = await fetch(`${API_BASE}/reply/multi`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return await handle(res);
}

export async function sendFeedback(payload) {
  const res = await fetch(`${API_BASE}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return await handle(res);
}

export async function saveReplyExample(payload) {
  const res = await fetch(`${API_BASE}/reply/save_example`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return await handle(res);
}

export async function fetchThreadSummary(threadId, provider = "gmail", email = null, userId = "") {
  const res = await fetch(`${API_BASE}/thread/summary`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ thread_id: threadId, provider, email, user_id: userId }),
  });
  return await handle(res);
}

export async function fetchFullThread(threadId, provider = "gmail", userId = "") {
  const res = await fetch(
    `${API_BASE}/thread/full?thread_id=${encodeURIComponent(threadId)}&provider=${encodeURIComponent(provider)}&user_id=${encodeURIComponent(userId)}`
  );
  return await handle(res);
}

export async function createFollowup(payload) {
  const res = await fetch(`${API_BASE}/followups/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return await handle(res);
}

export async function fetchFollowups(status = "", userId = "") {
  const res = await fetch(`${API_BASE}/followups?status=${encodeURIComponent(status)}&user_id=${encodeURIComponent(userId)}`);
  return await handle(res);
}

export async function fetchDueFollowups(userId = "") {
  const res = await fetch(`${API_BASE}/followups/due?user_id=${encodeURIComponent(userId)}`);
  return await handle(res);
}

export async function updateFollowupStatus(id, status, userId = "") {
  const res = await fetch(`${API_BASE}/followups/${encodeURIComponent(id)}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status, user_id: userId }),
  });
  return await handle(res);
}

export async function fetchAnalytics(days = 14, userId = "") {
  const res = await fetch(`${API_BASE}/analytics?days=${encodeURIComponent(days)}&user_id=${encodeURIComponent(userId)}`);
  return await handle(res);
}

export async function composeFromNotes(payload) {
  const res = await fetch(`${API_BASE}/compose/from-notes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return await handle(res);
}


export async function analyzeAttachment(payload) {
  const res = await fetch(`${API_BASE}/attachments/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return await handle(res);
}

export async function analyzeAllAttachments(payload) {
  const res = await fetch(`${API_BASE}/attachments/analyze-all`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return await handle(res);
}

export async function createGmailReplyDraft(payload) {
  const res = await fetch(`${API_BASE}/gmail/reply-draft`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return await handle(res);
}

export function googleConnectUrl(userId) {
  return `${API_BASE}/integrations/google/connect?user_id=${encodeURIComponent(userId)}`;
}

export async function fetchGoogleStatus(userId) {
  const res = await fetch(`${API_BASE}/integrations/google/status?user_id=${encodeURIComponent(userId)}`);
  return await handle(res);
}

export async function disconnectGoogle(userId) {
  const res = await fetch(`${API_BASE}/integrations/google?user_id=${encodeURIComponent(userId)}`, { method: "DELETE" });
  return await handle(res);
}


export function yahooConnectUrl(userId) {
  return `${API_BASE}/integrations/yahoo/connect?user_id=${encodeURIComponent(userId)}`;
}

export async function fetchYahooStatus(userId) {
  const res = await fetch(`${API_BASE}/integrations/yahoo/status?user_id=${encodeURIComponent(userId)}`);
  return await handle(res);
}

export async function disconnectYahoo(userId) {
  const res = await fetch(`${API_BASE}/integrations/yahoo?user_id=${encodeURIComponent(userId)}`, { method: "DELETE" });
  return await handle(res);
}
