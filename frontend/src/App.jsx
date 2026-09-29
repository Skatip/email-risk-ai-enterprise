import { useEffect, useMemo, useState } from "react";
import {
  fetchInbox,
  analyzeEmail,
  fetchAnalytics,
  fetchDueFollowups,
  fetchFollowups,
  fetchMeetings,
  updateFollowupStatus,
  googleConnectUrl,
  fetchGoogleStatus,
  disconnectGoogle,
  fetchRagStatus,
  syncEmailRag,
  askEmailAi,
} from "./api";

import EmailCard from "./components/EmailCard";
import DetailPanel from "./components/DetailPanel";
import ProviderLogo from "./components/ProviderLogo";
import "./styles.css";

const PROVIDERS = [
  {
    id: "gmail",
    name: "Gmail",
    logo: "gmail",
    email: import.meta.env.VITE_GMAIL_USER || "",
    color: "gmail",
    enabled: true,
    description:
      "Analyze Gmail inbox with priority, risk, replies, summaries, and reminders.",
  },
  {
    id: "outlook",
    name: "Outlook",
    logo: "outlook",
    email: import.meta.env.VITE_OUTLOOK_USER || "",
    color: "outlook",
    enabled: false,
    description:
      "Microsoft OAuth connection is coming next. No app passwords or manual keys will be required.",
  },
];

function pct(x) {
  return `${Math.round(Number(x || 0) * 100)}%`;
}

function fmtTime(ts) {
  if (!ts) return "No time";

  const n = Number(ts) * 1000;

  if (!Number.isFinite(n)) {
    return "No time";
  }

  return new Date(n).toLocaleString();
}

function reminderStateText(f) {
  const status = String(f?.status || "pending").toLowerCase();
  const eventAt = Number(f?.event_at || f?.remind_at || 0);
  const now = Date.now() / 1000;
  if (status === "missed") return "Missed / overdue";
  if (status === "due") return "Due now";
  if (status === "done") return "Done";
  if (eventAt > now) {
    const mins = Math.max(1, Math.round((eventAt - now) / 60));
    if (mins <= 60) return `In ${mins} min`;
  }
  return status;
}

function attachmentSearchText(it) {
  const attachments = Array.isArray(it?.attachments)
    ? it.attachments
    : [];

  const analyses = Array.isArray(it?.attachment_analysis)
    ? it.attachment_analysis
    : [];

  return [
    ...attachments.map(
      (a) =>
        `${a?.filename || ""} ${a?.file_type || ""} ${
          a?.mime_type || ""
        }`
    ),

    ...analyses.map(
      (a) =>
        `${a?.filename || ""} ${a?.document_type || ""} ${
          a?.document_label || ""
        } ${a?.summary || ""}`
    ),
  ].join(" ");
}

function ThemeToggle({ theme, toggleTheme }) {
  return (
    <button
      className="themeToggle"
      onClick={toggleTheme}
    >
      {theme === "dark" ? "☀️ Light" : "🌙 Dark"}
    </button>
  );
}

function StatCard({ label, value, sub }) {
  return (
    <div className="statCard">
      <span>{label}</span>
      <b>{value}</b>
      {sub && <small>{sub}</small>}
    </div>
  );
}

function MiniBar({ label, value, max }) {
  const width =
    max > 0
      ? Math.max(
          4,
          Math.round(
            (Number(value || 0) / max) * 100
          )
        )
      : 0;

  return (
    <div className="miniBarRow">
      <span>{label}</span>

      <div className="miniBarTrack">
        <i
          style={{
            width: `${width}%`,
          }}
        />
      </div>

      <b>{value}</b>
    </div>
  );
}

function LandingPage({
  onChoose,
  onConnectGmail,
  theme,
  toggleTheme,
}) {
  return (
    <main className="landingPage">
      <div className="landingTheme">
        <ThemeToggle
          theme={theme}
          toggleTheme={toggleTheme}
        />
      </div>

      <section className="heroCard">
        <div className="heroKicker">
          AI Email Command Center
        </div>

        <h1>Choose your workspace</h1>

        <p>
          Start with Gmail or Outlook now. Later, Slack and
          Jira can plug into the same launcher.
        </p>

        <div className="providerGrid">
          {PROVIDERS.map((p) => (
            <button
              key={p.id}
              className={`providerTile ${p.color}${p.enabled === false ? " disabled" : ""}`}
              disabled={p.enabled === false}
              onClick={() =>
                p.id === "gmail"
                  ? onConnectGmail()
                  : onChoose(p)
              }
            >
              <div className="providerIcon">
                <ProviderLogo
                  type={p.logo}
                  size={34}
                />
              </div>

              <div>
                <h2>{p.name}</h2>
                <p>{p.description}</p>
                <small>{p.email}</small>
              </div>
            </button>
          ))}

          <button
            className="providerTile disabled"
            disabled
          >
            <div className="providerIcon">
              <ProviderLogo
                type="slack"
                size={34}
              />
            </div>

            <div>
              <h2>Slack</h2>
              <p>
                Coming later for action items and team
                messages.
              </p>
            </div>
          </button>

          <button
            className="providerTile disabled"
            disabled
          >
            <div className="providerIcon">
              <ProviderLogo
                type="jira"
                size={34}
              />
            </div>

            <div>
              <h2>Jira</h2>
              <p>
                Coming later for issue creation and task
                tracking.
              </p>
            </div>
          </button>
        </div>
      </section>
    </main>
  );
}

function AnalyticsPanel({
  analytics,
  loading,
}) {
  if (loading) {
    return (
      <div className="panelCard">
        Loading analytics...
      </div>
    );
  }

  if (!analytics) {
    return (
      <div className="panelCard">
        No analytics yet. Refresh inbox first.
      </div>
    );
  }

  const intents = analytics.intent_counts || {};

  const maxIntent = Math.max(
    1,
    ...Object.values(intents).map(Number)
  );

  const senders = analytics.top_senders || [];

  const maxSender = Math.max(
    1,
    ...senders.map((x) =>
      Number(x.count || 0)
    )
  );

  return (
    <div className="dashboardGrid">
      <StatCard
        label="Analyzed Emails"
        value={analytics.total || 0}
      />

      <StatCard
        label="High Priority"
        value={analytics.high_priority || 0}
      />

      <StatCard
        label="Risky Emails"
        value={analytics.risky || 0}
      />

      <StatCard
        label="Safe Emails"
        value={analytics.safe || 0}
      />

      <div className="panelCard wide">
        <h3>Intent Trends</h3>

        {Object.entries(intents).length === 0 && (
          <p>No intent data yet.</p>
        )}

        {Object.entries(intents).map(
          ([k, v]) => (
            <MiniBar
              key={k}
              label={k}
              value={v}
              max={maxIntent}
            />
          )
        )}
      </div>

      <div className="panelCard wide">
        <h3>Top Sender Domains</h3>

        {senders.length === 0 && (
          <p>No sender data yet.</p>
        )}

        {senders.map((s) => (
          <MiniBar
            key={s.sender}
            label={s.sender}
            value={s.count}
            max={maxSender}
          />
        ))}
      </div>

      <div className="panelCard full">
        <h3>Daily Trend</h3>

        <div className="trendGrid">
          {(analytics.daily_trend || []).map(
            (d) => (
              <div
                key={d.date}
                className="trendItem"
              >
                <b>{d.date}</b>
                <span>Total: {d.total}</span>
                <span>High: {d.high}</span>
                <span>Risky: {d.risky}</span>
                <span>
                  Avg Priority:{" "}
                  {pct(d.avg_priority)}
                </span>
              </div>
            )
          )}
        </div>
      </div>
    </div>
  );
}

function MeetingsPanel({ meetings, onRefresh }) {
  const now = Date.now() / 1000;
  return (
    <div className="panelCard full">
      <div className="panelHeader">
        <div><h3>Meetings</h3><p>Scheduled meetings stay here independently of inbox filters and follow-ups.</p></div>
        <button className="softBtn" onClick={onRefresh}>Refresh meetings</button>
      </div>
      {meetings.length === 0 && <div className="emptyState">No meetings detected yet.</div>}
      {meetings.map((m) => {
        const past = Number(m.due_at || 0) > 0 && Number(m.due_at) < now;
        return (
          <div key={`${m.email_id}-${m.kind}`} className={`followupRow ${past ? "past_unknown" : "pending"}`}>
            <div>
              <b>{m.title || "Meeting"}</b>
              <p>{past ? "Meeting ended · attendance unknown" : "Scheduled meeting"}</p>
              <small>{m.source_sender || "email"} • {fmtTime(m.due_at)}{m.timezone ? ` • ${m.timezone}` : ""}</small>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function FollowupPanel({
  followups,
  onDone,
  onRefresh,
}) {
  return (
    <div className="panelCard full">
      <div className="panelHeader">
        <div>
          <h3>
            Follow-ups
          </h3>

          <p>
            Unresolved actions that still need your attention.
          </p>
        </div>

        <button
          className="softBtn"
          onClick={onRefresh}
        >
          Refresh follow-ups
        </button>
      </div>

      {followups.length === 0 && (
        <div className="emptyState">
          No follow-ups right now.
        </div>
      )}

      {followups.map((f) => (
        <div
          key={f.id}
          className={`followupRow ${f.status}`}
        >
          <div>
            <b>
              {f.subject ||
                f.email_id ||
                "Email follow-up"}
            </b>

            <p>{f.note || "No note"}</p>

            <small>
              {f.sender || f.provider || "email"}{" "}
              • {f.event_at ? "event" : "due"} {fmtTime(f.event_at || f.remind_at)}
              {f.event_timezone ? ` • ${f.event_timezone}` : ""}
              {f.remind_at && f.event_at && Number(f.remind_at) !== Number(f.event_at) ? ` • reminder ${fmtTime(f.remind_at)}` : ""}
              {` • ${reminderStateText(f)}`}
            </small>
          </div>

          {f.status !== "done" && (
            <button
              className="softBtn primary"
              onClick={() =>
                onDone(f.id)
              }
            >
              Mark done
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

export default function App() {
  /*
   * Account-bound testing identity.
   *
   * A fresh opaque id is created for every new Google OAuth connection.
   * The callback returns that id and it becomes the active workspace id.
   * This prevents a second Gmail account in the same browser from silently
   * restoring the first account's inbox, calendar, follow-ups, or analytics.
   */
  const [userId, setUserId] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    const callbackUserId = params.get("user_id");
    const gmailConnected = params.get("gmail") === "connected";

    if (gmailConnected && callbackUserId) {
      localStorage.setItem("email_ai_user_id", callbackUserId);
      return callbackUserId;
    }

    return localStorage.getItem("email_ai_user_id") || "";
  });

  const [theme, setTheme] = useState(
    () =>
      localStorage.getItem("theme") ||
      "dark"
  );

  const [workspace, setWorkspace] =
    useState(null);

  /*
   * Prevent the landing page from flashing before
   * we know whether Gmail is already connected.
   */
  const [
    checkingGoogle,
    setCheckingGoogle,
  ] = useState(true);

  const [items, setItems] =
    useState([]);

  const [selectedId, setSelectedId] =
    useState(null);

  const [loading, setLoading] =
    useState(false);

  const [err, setErr] =
    useState("");

  const [query, setQuery] =
    useState("");

  const [
    labelFilter,
    setLabelFilter,
  ] = useState("FOCUS");

  const [
    maxResults,
    setMaxResults,
  ] = useState(10);

  const [tab, setTab] =
    useState("inbox");

  const [ragStatus, setRagStatus] = useState(null);
  const [ragSyncing, setRagSyncing] = useState(false);
  const [chatQuestion, setChatQuestion] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [chatMessages, setChatMessages] = useState([]);

  async function loadRagStatus() {
    if (!userId) return;
    try { setRagStatus(await fetchRagStatus(userId)); } catch (e) { setErr(e.message); }
  }

  async function syncRagHistory() {
    if (!userId || ragSyncing) return;
    setRagSyncing(true); setErr("");
    try {
      const result = await syncEmailRag({ userId, maxMessages: 500, query: "in:anywhere" });
      setRagStatus({ indexed: (result.already_indexed || 0) + (result.indexed || 0), rag_version: result.rag_version });
    } catch (e) { setErr(e.message); } finally { setRagSyncing(false); }
  }

  async function submitEmailQuestion(e) {
    e?.preventDefault();
    const q = chatQuestion.trim();
    if (!q || !userId || chatLoading) return;
    setChatQuestion(""); setChatLoading(true); setErr("");
    setChatMessages((m) => [...m, { role: "user", text: q }]);
    try {
      const result = await askEmailAi({ userId, question: q, userTimezone: Intl.DateTimeFormat().resolvedOptions().timeZone });
      setChatMessages((m) => [...m, { role: "assistant", text: result.answer, sources: result.sources || [] }]);
    } catch (e2) { setErr(e2.message); } finally { setChatLoading(false); }
  }

  const [
    analytics,
    setAnalytics,
  ] = useState(null);

  const [
    analyticsLoading,
    setAnalyticsLoading,
  ] = useState(false);

  const [
    followups,
    setFollowups,
  ] = useState([]);

  const [meetings, setMeetings] = useState([]);
  const [reminders, setReminders] = useState([]);

  const provider =
    workspace?.id || "gmail";

  const activeEmail =
    workspace?.email || "";

  function beginGoogleConnection() {
    const freshUserId = crypto.randomUUID();
    localStorage.setItem("email_ai_pending_user_id", freshUserId);
    window.location.href = googleConnectUrl(freshUserId);
  }

  async function switchConnectedAccount() {
    setErr("");
    try {
      if (userId) {
        await disconnectGoogle(userId);
      }
    } catch (e) {
      console.log("Previous mail connection could not be disconnected:", e);
    }

    localStorage.removeItem("email_ai_user_id");
    localStorage.removeItem("email_ai_pending_user_id");
    setItems([]);
    setSelectedId(null);
    setAnalytics(null);
    setFollowups([]);
    setMeetings([]);
    setReminders([]);
    setWorkspace(null);
    setUserId("");

    beginGoogleConnection();
  }

  /*
   * Theme
   */
  useEffect(() => {
    document.documentElement.setAttribute(
      "data-theme",
      theme
    );

    localStorage.setItem(
      "theme",
      theme
    );
  }, [theme]);

  /*
   * Restore Gmail connection after:
   *
   * - OAuth callback
   * - browser refresh
   * - returning to the application later
   *
   * This is what prevents:
   *
   * Gmail OAuth
   * → frontend
   * → landing page
   * → Gmail OAuth again
   */
  useEffect(() => {
    let cancelled = false;

    async function restoreGoogleSession() {
      if (!userId) {
        if (!cancelled) setCheckingGoogle(false);
        return;
      }

      const params = new URLSearchParams(window.location.search);
      const callbackProvider =
        params.get("gmail") === "connected" ? "gmail" : "";

      try {
        let status = null;
        let restoredProvider = null;

        if (callbackProvider === "gmail") {
          status = await fetchGoogleStatus(userId);
          restoredProvider = PROVIDERS.find((p) => p.id === "gmail");
        } else {
          const googleStatus = await fetchGoogleStatus(userId).catch(() => null);
          if (googleStatus?.connected) {
            status = googleStatus;
            restoredProvider = PROVIDERS.find((p) => p.id === "gmail");
          }
        }

        if (cancelled) return;

        if (status?.connected && restoredProvider) {
          setWorkspace({
            ...restoredProvider,
            email: status.email || restoredProvider.email || "",
          });

          if (
            params.has("gmail") ||
            params.has("email") ||
            params.has("user_id")
          ) {
            window.history.replaceState({}, document.title, window.location.pathname);
          }
        }
      } catch (e) {
        console.log("Mail connection not restored:", e);
      } finally {
        if (!cancelled) setCheckingGoogle(false);
      }
    }

    restoreGoogleSession();

    return () => {
      cancelled = true;
    };
  }, [userId]);

  function toggleTheme() {
    setTheme((prev) =>
      prev === "dark"
        ? "light"
        : "dark"
    );
  }

  async function loadInbox() {
    if (!workspace) {
      return;
    }

    setLoading(true);
    setErr("");

    try {
      const data =
        await fetchInbox({
          maxResults,
          userEmail:
            activeEmail,
          provider,
          userId,
          bucket: labelFilter,
        });

      const next =
        Array.isArray(data)
          ? data
          : data?.items || [];

      setItems(next);

      setSelectedId((prev) =>
        next.some(
          (x) => x.id === prev
        )
          ? prev
          : next[0]?.id ||
            null
      );

      // Inbox rendering ends here. Do not start mailbox-wide RAG or meeting
      // reconciliation on this critical path. Ask Email-AI has an explicit history sync,
      // and Meetings reconciles when that surface is opened.
    } catch (e) {
      setErr(
        String(
          e?.message ||
            `Failed to load ${provider}`
        )
      );
    } finally {
      setLoading(false);
    }
  }

  async function openAndAnalyzeEmail(email) {
    if (!email?.id) return;
    setSelectedId(email.id);
    if (email.analysis_status === "done" || email.analysis_status === "loading") return;
    setItems((prev) => prev.map((x) => x.id === email.id ? { ...x, analysis_status: "loading" } : x));
    try {
      const analyzed = await analyzeEmail({ email, provider, user_email: activeEmail, user_id: userId });
      setItems((prev) => prev.map((x) => {
        if (x.id !== email.id) return x;
        // Deep analysis enriches the selected card, but opening/reading must never
        // silently move it out of the current inbox/filter. Routing changes apply
        // on the next explicit inbox refresh.
        const routing = {
          bucket: x.bucket,
          inbox_score: x.inbox_score,
          respond_recommended: x.respond_recommended,
          reply_decision: x.reply_decision,
          requires_action: x.requires_action,
          direct_human: x.direct_human,
        };
        return { ...x, ...analyzed, ...routing, analysis_status: "done" };
      }));
    } catch (e) {
      console.error("Deep email analysis failed:", e);
      setItems((prev) => prev.map((x) => x.id === email.id ? { ...x, analysis_status: "error" } : x));
    }
  }

  async function loadAnalytics() {
    setAnalyticsLoading(true);

    try {
      setAnalytics(
        await fetchAnalytics(14, userId)
      );
    } catch (e) {
      setErr(
        String(
          e?.message || e
        )
      );
    } finally {
      setAnalyticsLoading(false);
    }
  }

  async function loadFollowups() {
    try {
      await fetchDueFollowups(userId);
      const rows = await fetchFollowups("", userId);
      setReminders(rows || []);
      // New canonical follow-ups are explicitly typed. Legacy generic `email`
      // reminders are intentionally not shown as follow-ups because they may have
      // been created by the old one-hour/default-reminder behavior.
      setFollowups((rows || []).filter((f) => String(f?.reminder_kind || "").toLowerCase() === "followup"));
    } catch (e) {
      setErr(String(e?.message || e));
    }
  }

  async function loadMeetings() {
    try {
      setMeetings(await fetchMeetings(userId, 100));
    } catch (e) {
      setErr(String(e?.message || e));
    }
  }

  /*
   * Once a workspace exists,
   * automatically load its data.
   */
  useEffect(() => {
    if (workspace) {
      loadInbox();
      loadAnalytics();
      loadFollowups();
      // Meetings are reconciled lazily when the Meetings tab is opened. This keeps
      // Gmail/ICS work off the inbox startup path.
    }

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    workspace?.id,
    workspace?.email,
    maxResults,
    labelFilter,
  ]);

  // Lightweight in-app reminder clock. No Celery/Redis is required: while the
  // app is open, refresh reminder state every 30 seconds so due/missed changes
  // surface without waiting for a day change or manual refresh.
  useEffect(() => {
    if (!workspace) return undefined;
    const timer = window.setInterval(() => {
      loadFollowups();
    }, 30000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspace?.id, workspace?.email, userId]);

  const filtered = useMemo(() => {
    let res = [...items];

    const q =
      query
        .trim()
        .toLowerCase();

    if (q) {
      res = res.filter((it) =>
        [
          it.subject,
          it.from,
          it.snippet,
          it.body,
          attachmentSearchText(it),
        ].some((x) =>
          String(x || "")
            .toLowerCase()
            .includes(q)
        )
      );
    }

    if (labelFilter !== "ALL") {
      const bucket = (it) => String(it?.bucket || "").toUpperCase();

      if (labelFilter === "FOCUS") {
        const focusBuckets = new Set([
          "IMPORTANT_NOW",
          "CONVERSATIONAL",
          "BUSINESS",
          "RECRUITING",
          "SECURITY",
          "FOLLOW_UP",
          "TRANSACTIONAL",
        ]);
        res = res.filter((it) =>
          focusBuckets.has(bucket(it)) &&
          (Number(it?.inbox_score || 0) >= 0.38 ||
            it?.requires_action === true ||
            it?.direct_human === true ||
            it?.security_event === true)
        );
      } else if (labelFilter === "NEEDS_REPLY") {
        res = res.filter(
          (it) =>
            it?.respond_recommended === true ||
            String(it?.reply_decision || "").toUpperCase() === "DRAFT_REPLY"
        );
      } else if (labelFilter === "PEOPLE") {
        res = res.filter(
          (it) =>
            it?.direct_human === true ||
            ["CONVERSATIONAL", "FOLLOW_UP"].includes(bucket(it))
        );
      } else if (labelFilter === "WORK_CAREER") {
        res = res.filter((it) =>
          ["BUSINESS", "RECRUITING"].includes(bucket(it))
        );
      } else if (labelFilter === "MONEY_SECURITY") {
        res = res.filter((it) =>
          ["TRANSACTIONAL", "SECURITY"].includes(bucket(it))
        );
      } else if (labelFilter === "UPDATES") {
        res = res.filter((it) =>
          [
            "INFORMATIONAL",
            "JOB_FEED",
            "MARKETING",
            "SOCIAL",
            "AUTOMATED_LOW_VALUE",
          ].includes(bucket(it))
        );
      }
    }

    return res;
  }, [
    items,
    query,
    labelFilter,
  ]);

  const selectedItem =
    useMemo(
      () =>
        items.find(
          (it) =>
            it.id === selectedId
        ) || null,
      [items, selectedId]
    );

  const activeReminder = useMemo(() => {
    const live = (reminders || []).filter((f) => !["done", "dismissed"].includes(String(f?.status || "").toLowerCase()));
    const missed = live.find((f) => String(f?.status || "").toLowerCase() === "missed");
    if (missed) return { ...missed, ui_state: "missed" };
    const due = live.find((f) => String(f?.status || "").toLowerCase() === "due");
    if (due) return { ...due, ui_state: "due" };
    const now = Date.now() / 1000;
    const upcoming = live
      .filter((f) => Number(f?.event_at || f?.remind_at || 0) > now)
      .sort((a, b) => Number(a?.event_at || a?.remind_at || 0) - Number(b?.event_at || b?.remind_at || 0))[0];
    if (upcoming && Number(upcoming?.event_at || upcoming?.remind_at || 0) - now <= 1800) {
      return { ...upcoming, ui_state: "upcoming" };
    }
    return null;
  }, [reminders]);

  const counts = useMemo(() => {
    const high =
      items.filter(
        (x) =>
          x.label === "HIGH"
      ).length;

    const risky =
      items.filter(
        (x) =>
          Number(x.risk || 0) >=
          0.5
      ).length;

    return {
      total: items.length,
      high,
      risky,
    };
  }, [items]);

  /*
   * Wait until the backend tells us whether
   * Gmail is already connected.
   */
  if (checkingGoogle) {
    return (
      <main className="landingPage">
        <section className="heroCard">
          <div className="heroKicker">
            AI Email Command Center
          </div>

          <h1>
            Checking Gmail connection...
          </h1>

          <p>
            Verifying your secure Google
            connection.
          </p>
        </section>
      </main>
    );
  }

  /*
   * No connected/restored workspace:
   * show provider launcher.
   */
  if (!workspace) {
    return (
      <LandingPage
        onChoose={setWorkspace}
        onConnectGmail={beginGoogleConnection}
        theme={theme}
        toggleTheme={
          toggleTheme
        }
      />
    );
  }

  return (
    <div className="appShell">
      <header className="appHeader">
        <button
          className="backBtn"
          onClick={() =>
            setWorkspace(null)
          }
        >
          ← Workspaces
        </button>

        <div className="brandBlock">
          <div
            className={`brandIcon ${provider}`}
          >
            <ProviderLogo
              type={
                workspace.logo ||
                provider
              }
              size={30}
            />
          </div>

          <div>
            <h1>
              {workspace.name} AI
              Inbox
            </h1>

            <p>{activeEmail}</p>
          </div>
        </div>

        <div className="headerRight">
          <button
            className="softBtn"
            onClick={switchConnectedAccount}
            title="Disconnect this Gmail workspace and connect a different Google account"
          >
            Switch account
          </button>

          <ThemeToggle
            theme={theme}
            toggleTheme={
              toggleTheme
            }
          />

          <div className="headerStats">
            <StatCard
              label="Emails"
              value={
                counts.total
              }
            />

            <StatCard
              label="High"
              value={
                counts.high
              }
            />

            <StatCard
              label="Risky"
              value={
                counts.risky
              }
            />
          </div>
        </div>
      </header>

      <nav className="tabBar">
        <button
          className={
            tab === "inbox"
              ? "active"
              : ""
          }
          onClick={() =>
            setTab("inbox")
          }
        >
          Inbox
        </button>

        <button
          className={tab === "meetings" ? "active" : ""}
          onClick={() => { setTab("meetings"); loadMeetings(); }}
        >
          Meetings
        </button>

        <button
          className={
            tab === "followups"
              ? "active"
              : ""
          }
          onClick={() => {
            setTab(
              "followups"
            );

            loadFollowups();
          }}
        >
          Follow-ups
        </button>

        <button
          className={
            tab === "analytics"
              ? "active"
              : ""
          }
          onClick={() => {
            setTab(
              "analytics"
            );

            loadAnalytics();
          }}
        >
          Analytics
        </button>

        <button
          className={tab === "ask" ? "active" : ""}
          onClick={() => { setTab("ask"); loadRagStatus(); }}
        >
          Ask Email-AI
        </button>
      </nav>

      {activeReminder && (
        <div className={`reminderBanner ${activeReminder.ui_state}`}>
          <div>
            <b>
              {activeReminder.ui_state === "missed"
                ? "Missed follow-up"
                : activeReminder.ui_state === "due"
                  ? "Reminder due now"
                  : "Upcoming reminder"}
            </b>
            <span>{activeReminder.subject || "Email follow-up"}</span>
            <small>
              {activeReminder.note || ""}
              {` • ${fmtTime(activeReminder.event_at || activeReminder.remind_at)}`}
            </small>
          </div>
          <button className="softBtn" type="button" onClick={() => { setTab("followups"); loadFollowups(); }}>
            View
          </button>
        </div>
      )}

      {err && (
        <div className="errorBanner">
          {err}
        </div>
      )}

      {tab === "inbox" && (
        <>
          <section className="toolbar">
            <input
              className="searchInput"
              placeholder={`Search ${workspace.name} emails...`}
              value={query}
              onChange={(e) =>
                setQuery(
                  e.target.value
                )
              }
            />

            <select
              className="selectInput inboxViewSelect"
              aria-label="Inbox view"
              title="Choose a focused inbox view"
              value={labelFilter}
              onChange={(e) =>
                setLabelFilter(
                  e.target.value
                )
              }
            >
              <option value="FOCUS">Focus — Important</option>
              <option value="NEEDS_REPLY">Needs Reply</option>
              <option value="PEOPLE">People & Conversations</option>
              <option value="WORK_CAREER">Work & Career</option>
              <option value="MONEY_SECURITY">Money & Security</option>
              <option value="UPDATES">Updates & Low Priority</option>
              <option value="ALL">All Mail</option>
            </select>

            <select
              className="selectInput"
              value={maxResults}
              onChange={(e) =>
                setMaxResults(
                  Number(
                    e.target.value
                  )
                )
              }
            >
              <option value={5}>
                5 Emails
              </option>

              <option value={10}>
                10 Emails
              </option>

              <option value={20}>
                20 Emails
              </option>

              <option value={50}>
                50 Emails
              </option>
            </select>

            <button
              className="primaryBtn"
              onClick={loadInbox}
              disabled={loading}
            >
              {loading
                ? "Fetching..."
                : "Refresh"}
            </button>
          </section>

          <main className="contentGrid">
            <section className="listPane">
              {filtered.map(
                (it) => (
                  <EmailCard
                    key={it.id}
                    item={it}
                    selected={
                      selectedId ===
                      it.id
                    }
                    onSelect={() => openAndAnalyzeEmail(it)}
                    onPatchItem={(
                      patch
                    ) =>
                      setItems(
                        (prev) =>
                          prev.map(
                            (x) =>
                              x.id ===
                              it.id
                                ? {
                                    ...x,
                                    ...patch,
                                  }
                                : x
                          )
                      )
                    }
                    onFollowupCreated={
                      loadFollowups
                    }
                    userId={userId}
                  />
                )
              )}

              {loading && (
                <div className="emptyState">
                  Fetching emails...
                </div>
              )}

              {!loading &&
                filtered.length ===
                  0 && (
                  <div className="emptyState">
                    No{" "}
                    {workspace.name}{" "}
                    emails found.
                  </div>
                )}
            </section>

            <DetailPanel
              item={
                selectedItem
              }
            />
          </main>
        </>
      )}

      {tab === "meetings" && (
        <main className="pagePanel">
          <MeetingsPanel meetings={meetings} onRefresh={loadMeetings} />
        </main>
      )}

      {tab === "followups" && (
        <main className="pagePanel">
          <FollowupPanel
            followups={
              followups
            }
            onRefresh={
              loadFollowups
            }
            onDone={async (
              id
            ) => {
              await updateFollowupStatus(
                id,
                "done",
                userId
              );

              await loadFollowups();
            }}
          />
        </main>
      )}

      {tab === "ask" && (
        <section className="askEmailAiPage">
          <div className="askEmailAiHeader">
            <div>
              <h2>Ask Email-AI</h2>
              <p>Ask natural-language questions across your indexed old and current emails. Answers are grounded in retrieved email evidence.</p>
            </div>
            <div className="ragStatusBox">
              <b>{ragStatus?.indexed || 0}</b><span> emails indexed</span>
              <button className="softBtn" disabled={ragSyncing} onClick={syncRagHistory}>
                {ragSyncing ? "Syncing history…" : "Sync email history"}
              </button>
            </div>
          </div>
          <div className="askConversation">
            {chatMessages.length === 0 && (
              <div className="askEmpty">Try: “What did the recruiter say about my interview?”, “Which bills need attention?”, or “Find the latest conversation about the project deadline.”</div>
            )}
            {chatMessages.map((m, i) => (
              <div key={i} className={`chatBubble ${m.role}`}>
                <div>{m.text}</div>
                {m.sources?.length > 0 && (
                  <div className="chatSources">
                    {m.sources.slice(0, 6).map((src, j) => (
                      <div key={`${src.email_id}-${j}`} className="chatSource">
                        <b>[{j + 1}] {src.subject || "(no subject)"}</b>
                        <span>{src.from || "Unknown sender"}{src.ts ? ` • ${fmtTime(src.ts)}` : ""}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {chatLoading && <div className="chatBubble assistant">Searching your emails…</div>}
          </div>
          <form className="askComposer" onSubmit={submitEmailQuestion}>
            <input value={chatQuestion} onChange={(e) => setChatQuestion(e.target.value)} placeholder="Ask about your emails…" />
            <button className="softBtn primary" type="submit" disabled={chatLoading || !chatQuestion.trim()}>Ask</button>
          </form>
        </section>
      )}

      {tab === "analytics" && (
        <main className="pagePanel">
          <AnalyticsPanel
            analytics={
              analytics
            }
            loading={
              analyticsLoading
            }
          />
        </main>
      )}
    </div>
  );
}