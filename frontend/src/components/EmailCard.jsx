import { useEffect, useMemo, useState } from "react";
import * as BadgeModule from "./Badge";
import {
  generateReply,
  fetchMultiReply,
  sendFeedback,
  saveReplyExample,
  fetchThreadSummary,
  createFollowup,
  analyzeAttachment,
  analyzeAllAttachments,
  createGmailReplyDraft,
} from "../api";

const Badge = BadgeModule.Badge || BadgeModule.default;

function pct(x) {
  const n = Number(x || 0);
  return `${Math.round(n * 100)}%`;
}

function decodeHtml(s) {
  const str = String(s || "");
  if (!str) return "";
  if (typeof document === "undefined") return str;
  if (!str.includes("&")) return str;
  const txt = document.createElement("textarea");
  txt.innerHTML = str;
  return txt.value;
}

function clampText(s, n = 170) {
  const str = decodeHtml((s || "").trim());
  if (!str) return "";
  return str.length > n ? str.slice(0, n - 1) + "…" : str;
}

function normalizeDraftPayload(payload) {
  const p = payload || {};
  const meta = p.meta || p.reply_meta || {};

  const replyText =
    p.reply ??
    p.text ??
    meta.reply ??
    meta.text ??
    meta.draft ??
    "";

  const tone = (meta.tone ?? p.tone ?? "professional") || "professional";

  let conf =
    meta.confidence ??
    meta.conf ??
    p.confidence ??
    p.conf ??
    0.85;

  conf = Number(conf || 0);
  if (conf > 1.0) conf = conf / 100.0;

  return {
    reply: String(replyText || ""),
    tone: String(tone),
    confidence: conf,
    decision: String(p.decision || meta.decision || "").toUpperCase(),
    clarification_question: String(p.clarification_question || meta.clarification_question || ""),
    reason: String(p.reason || p.understanding || meta.reason || ""),
    safety_blocked: Boolean(meta.safety_blocked ?? p.safety_blocked ?? false),
    safety_reason: String(meta.safety_reason ?? p.safety_reason ?? ""),
    reply_meta: meta.reply_meta ?? p.reply_meta ?? meta ?? null,
  };
}

function isSchedulingItem(item) {
  const semantic = [item?.intent, item?.message_type, item?.sender_expectation, item?.reason]
    .map((x) => String(x || "").toUpperCase())
    .join(" ");
  return ["MEETING", "SCHEDUL", "APPOINTMENT", "CALENDAR"].some((x) => semantic.includes(x));
}

function seedDraftFromItem(item) {
  if (!item) return null;
  // Never surface a pre-generated meeting acceptance before the user has made
  // the availability decision. Calendar-free is not user consent.
  if (isSchedulingItem(item) && item?.availability_confirmed_by_user !== true) return null;

  const replyText =
    item?.suggested_reply ??
    item?.reply?.text ??
    item?.reply?.reply ??
    item?.reply ??
    "";

  const meta =
    item?.suggested_reply_meta ??
    item?.reply?.meta ??
    item?.reply_meta ??
    null;

  if (!replyText && !meta) return null;

  return normalizeDraftPayload({
    reply: replyText,
    meta: meta || {},
  });
}

function priorityClass(label) {
  const v = String(label || "").toUpperCase();
  if (v === "HIGH") return "high";
  if (v === "MEDIUM") return "medium";
  return "low";
}

function riskClass(risk) {
  const n = Number(risk || 0);
  if (n >= 0.6) return "high";
  if (n >= 0.25) return "medium";
  return "low";
}

function senderTypeIcon(type) {
  if (type === "PERSONAL") return "👤";
  if (type === "COMPANY") return "🏢";
  if (type === "AUTOMATED") return "🤖";
  return "❔";
}


function shouldOfferReply(item) {
  const decision = String(item?.reply_decision || item?.decision || "").toUpperCase();
  if (["DRAFT_REPLY", "DRAFT_AND_ACTION"].includes(decision)) return true;
  if (["NO_REPLY", "ASK_USER", "ACTION_ONLY", "WAIT"].includes(decision)) return false;
  return item?.respond_recommended === true;
}

function replyButtonLabel(item, loadingDraft, hasDraft) {
  if (loadingDraft) return "Understanding...";
  const isFinal = item?.analysis_status === "done";
  const decision = String(item?.reply_decision || item?.decision || "").toUpperCase();
  if (!isFinal && ["NO_REPLY", "ASK_USER", "ACTION_ONLY", "WAIT"].includes(decision)) return "Check reply";
  if (decision === "ASK_USER") return "Needs your input";
  if (decision === "ACTION_ONLY") return "Action only";
  if (decision === "WAIT") return "Wait / no reply";
  if (!shouldOfferReply(item)) return "No reply needed";
  return hasDraft ? "Regenerate reply" : "Generate reply";
}

function noReplyReason(item) {
  const decision = String(item?.reply_decision || item?.decision || "").toUpperCase();
  if (decision === "ASK_USER") {
    return item?.clarification_question || item?.reason || "AI needs information from you before it can draft a grounded reply.";
  }
  if (decision === "ACTION_ONLY") return item?.reason || "The message requires an action rather than an email reply.";
  if (decision === "WAIT") return item?.reason || "The conversation should wait for now.";
  return item?.reason || item?.priority_reason || "AI determined that a reply is not necessary.";
}


function icon(cat) {
  if (cat === "IMPORTANT") return "⭐";
  if (cat === "LESS") return "🕓";
  if (cat === "SPAM") return "🚫";
  if (cat === "PROMO") return "🏷️";
  return "";
}

function formatThreadSummary(res) {
  if (!res || typeof res !== "object") {
    return "No summary returned.";
  }

  const summary = String(res.summary || "").trim();
  const actionItems = Array.isArray(res.action_items) ? res.action_items : [];
  const decisions = Array.isArray(res.decisions) ? res.decisions : [];
  const timeline = Array.isArray(res.timeline) ? res.timeline : [];
  const participants = Array.isArray(res.participants) ? res.participants : [];

  let out = "";

  if (summary) {
    out += `Summary:\n${summary}\n\n`;
  }

  if (actionItems.length) {
    out += "Action Items:\n";
    out += actionItems.map((x) => `- ${x}`).join("\n");
    out += "\n\n";
  }

  if (decisions.length) {
    out += "Decisions:\n";
    out += decisions.map((x) => `- ${typeof x === "string" ? x : JSON.stringify(x)}`).join("\n");
    out += "\n\n";
  }

  if (timeline.length) {
    out += "Timeline:\n";
    out += timeline.map((x) => {
      if (typeof x === "string") return `- ${x}`;
      return `- ${x.from || "Someone"}: ${x.event || x.subject || JSON.stringify(x)}`;
    }).join("\n");
    out += "\n\n";
  }

  if (participants.length) {
    out += "Participants:\n";
    out += participants.map((x) => `- ${x}`).join("\n");
  }

  return out.trim() || "No summary returned.";
}

function isFamilyPersonal(item) {
  const rel = String(item?.relationship_type || item?.relationship || "").toUpperCase();
  return ["FAMILY_PERSONAL", "FAMILY", "PERSONAL"].includes(rel);
}

function isSecurityRelated(item) {
  return item?.security_event === true;
}


function attachmentIcon(type) {
  const t = String(type || "").toLowerCase();
  if (t === "pdf") return "📄";
  if (t === "word") return "📝";
  if (t === "excel" || t === "csv") return "📊";
  if (t === "image") return "🖼️";
  if (t === "video") return "🎥";
  if (t === "archive") return "📦";
  if (t === "risky_executable") return "⚠️";
  return "📎";
}

function shortFileName(name, n = 36) {
  const s = String(name || "attachment");
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

function attachmentDocLabel(att, result) {
  return result?.document_label || att?.document_label || String(att?.file_type || "file").toUpperCase();
}

function uniqueAttachmentResults(item, localResults) {
  const local = Object.values(localResults || {}).filter(Boolean);
  const saved = Array.isArray(item?.attachment_analysis) ? item.attachment_analysis : [];
  const all = [...saved, ...local];
  const seen = new Set();
  const out = [];
  for (const x of all) {
    const key = String(x?.filename || "") + "|" + String(x?.document_type || "");
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(x);
  }
  return out;
}

export default function EmailCard({ item, onPatchItem, onFollowupCreated, selected, onSelect, userId = "" }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(() => seedDraftFromItem(item));
  const [loadingDraft, setLoadingDraft] = useState(false);
  const [err, setErr] = useState("");
  const [copied, setCopied] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editedText, setEditedText] = useState("");
  const [savingExample, setSavingExample] = useState(false);
  const [savedMsg, setSavedMsg] = useState("");

  const [threadSummary, setThreadSummary] = useState("");
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [followMsg, setFollowMsg] = useState("");
  const [multiReplies, setMultiReplies] = useState([]);
  const [loadingMulti, setLoadingMulti] = useState(false);
  const [attachmentResults, setAttachmentResults] = useState({});
  const [loadingAttachment, setLoadingAttachment] = useState("");
  const [loadingAllAttachments, setLoadingAllAttachments] = useState(false);
  const [gmailDraftMsg, setGmailDraftMsg] = useState("");
  const [creatingGmailDraft, setCreatingGmailDraft] = useState(false);
  const [calendarContext, setCalendarContext] = useState(null);
  const [availabilitySubmitting, setAvailabilitySubmitting] = useState(false);

  useEffect(() => {
    const d = seedDraftFromItem(item);
    setDraft(d);
    setEditing(false);
    setEditedText(d?.reply || "");
    setErr("");
    setCopied(false);
    setSavedMsg("");
    setThreadSummary("");
    setFollowMsg("");
    setMultiReplies([]);
    setAttachmentResults({});
    setLoadingAttachment("");
    setLoadingAllAttachments(false);
    setGmailDraftMsg("");
    setCreatingGmailDraft(false);
    setCalendarContext(null);
    setAvailabilitySubmitting(false);
  }, [item?.id]);

  const subject = decodeHtml(item?.subject || "(no subject)");
  const from = decodeHtml(item?.from || "(no sender)");
  const preview = useMemo(() => clampText(item?.snippet || ""), [item?.snippet]);

  const badgeTone =
    item?.label === "HIGH" ? "red" : item?.label === "MEDIUM" ? "yellow" : "green";

  const userCat = (item?.user_pref?.user_category || "").toUpperCase();
  const showPref = ["IMPORTANT", "LESS", "SPAM", "PROMO"].includes(userCat);

  const senderType =
    String(
      item?.human_signals?.sender_type ||
      item?.sender_type ||
      "UNKNOWN"
    ).toUpperCase();

  const canReply = shouldOfferReply(item);
  const replyNeedsFinalCheck = item?.analysis_status !== "done";
  const familyPersonal = isFamilyPersonal(item);
  const securityRelated = isSecurityRelated(item);
  const attachments = Array.isArray(item?.attachments) ? item.attachments : [];
  const attachmentAnalyses = uniqueAttachmentResults(item, attachmentResults);

  async function onAnalyzeAttachment(att) {
    const key = String(att?.attachment_id || att?.filename || "attachment");
    setErr("");
    setLoadingAttachment(key);

    try {
      const res = await analyzeAttachment({
        provider: item?.provider || "gmail",
        message_id: item?.id,
        attachment: att,
        sender_band: item?.sender_band || "",
        source_folder: item?.source_folder || "",
        email_subject: item?.subject || "",
        email_sender: item?.from || "",
        email_snippet: item?.snippet || "",
        user_id: userId,
      });

      setAttachmentResults((prev) => ({ ...prev, [key]: res }));

      const existing = Array.isArray(item?.attachment_analysis) ? item.attachment_analysis : [];
      const nextAnalysis = [...existing.filter((x) => x?.filename !== res?.filename), res];
      const boost = Math.max(Number(item?.attachment_priority_boost || 0), Number(res?.priority_boost || 0));
      const basePriority = Number(item?.priority || 0);
      const patchedPriority = Math.min(1, basePriority + boost);

      onPatchItem?.({
        attachment_analysis: nextAnalysis,
        attachment_priority_boost: boost,
        priority: patchedPriority,
        attachment_reply_context: nextAnalysis.map((x) => x?.reply_context).filter(Boolean).join("\n"),
      });
    } catch (e) {
      setErr(String(e?.message || e));
    } finally {
      setLoadingAttachment("");
    }
  }


  async function onAnalyzeAllAttachments() {
    if (!attachments.length) return;
    setErr("");
    setLoadingAllAttachments(true);
    try {
      const res = await analyzeAllAttachments({
        user_id: userId,
        email: {
          id: item?.id,
          threadId: item?.threadId || "",
          from: item?.from || "",
          subject: item?.subject || "",
          snippet: item?.snippet || "",
          body: item?.body || "",
          provider: item?.provider || "gmail",
          sender_band: item?.sender_band || "",
          source_folder: item?.source_folder || "",
          attachments,
        },
      });
      const analyses = Array.isArray(res?.attachment_analysis) ? res.attachment_analysis : [];
      const byKey = {};
      for (const r of analyses) {
        const att = attachments.find((a) => a?.filename === r?.filename);
        const key = String(att?.attachment_id || r?.filename || Math.random());
        byKey[key] = r;
      }
      setAttachmentResults((prev) => ({ ...prev, ...byKey }));
      const boost = analyses.reduce((m, x) => Math.max(m, Number(x?.priority_boost || 0)), 0);
      onPatchItem?.({
        attachment_analysis: analyses,
        attachment_bundle: res?.attachment_bundle || {},
        attachment_reply_context: res?.attachment_reply_context || res?.attachment_bundle?.reply_context || "",
        attachment_priority_boost: boost,
        priority: Math.min(1, Number(item?.priority || 0) + boost),
      });
    } catch (e) {
      setErr(String(e?.message || e));
    } finally {
      setLoadingAllAttachments(false);
    }
  }

  async function onCreateGmailDraft() {
    const replyText = String(editing ? editedText : draft?.reply || "").trim();
    if (!replyText) return;
    setErr("");
    setGmailDraftMsg("");
    setCreatingGmailDraft(true);
    try {
      const res = await createGmailReplyDraft({
        user_id: userId,
        thread_id: item?.threadId || "",
        message_id: item?.id || "",
        reply_text: replyText,
      });
      setGmailDraftMsg(`Saved to Gmail Drafts in this thread${res?.draft_id ? ` • ${res.draft_id}` : ""}`);
    } catch (e) {
      setErr(String(e?.message || e));
    } finally {
      setCreatingGmailDraft(false);
    }
  }

  async function onFeedback(clicked) {
    setErr("");
    try {
      const senderEmail = String(item?.from || "").match(/<([^>]+)>/)?.[1] || "";

      onPatchItem?.({
        user_pref: {
          user_category: clicked,
          user_category_confidence: 1.0,
          user_category_source: "manual",
          user_category_evidence: 1,
        },
      });

      await sendFeedback({
        action: "label_email",
        email_id: item?.id,
        sender_email: senderEmail,
        clicked,
        subject: item?.subject || "",
        snippet: item?.snippet || "",
        provider: item?.provider || "gmail",
        meta: { ui: "emailcard" },
      });
    } catch (e) {
      setErr(String(e?.message || e));
    }
  }

  async function onSaveExample(useEdited = false) {
    if (!draft?.reply && !editedText) return;
    setSavingExample(true);
    setSavedMsg("");
    setErr("");

    try {
      const inbound = [item?.subject || "", item?.snippet || ""]
        .filter(Boolean)
        .join("\n\n");

      const outbound = useEdited
        ? String(editedText || "").trim()
        : String(draft?.reply || "").trim();

      if (!outbound) throw new Error("Reply text is empty.");

      await saveReplyExample({
        inbound,
        outbound,
        label: "style",
        user_id: userId,
      });

      setSavedMsg("Saved to style memory");
    } catch (e) {
      setErr(String(e?.message || e));
    } finally {
      setSavingExample(false);
    }
  }

  async function persistSuggestedFollowup(out) {
    const follow = out?.follow_up || {};
    const remindAt = Number(follow?.remind_at_unix || 0);
    if (!follow?.needed || remindAt <= 0 || !item?.id || !userId) return;
    try {
      await createFollowup({
        email_id: item.id,
        thread_id: item?.threadId || "",
        remind_at: remindAt,
        note: follow?.note || follow?.reason || "Follow up on this email",
        subject: item?.subject || "",
        sender: item?.from || "",
        provider: item?.provider || "gmail",
        user_id: userId,
      });
      setFollowMsg("Reminder added automatically");
      onFollowupCreated?.();
    } catch (e) {
      console.warn("Automatic reminder creation skipped:", e);
    }
  }

  async function submitAvailabilityConfirmation(answer) {
    setAvailabilitySubmitting(true);
    setErr("");
    try {
      const email = {
        id: item?.id, from: item?.from, subject: item?.subject, snippet: item?.snippet,
        body: item?.body || "", ts: item?.ts, provider: item?.provider || "gmail",
        threadId: item?.threadId || "", attachments: item?.attachments || [],
        attachment_analysis: item?.attachment_analysis || [],
        attachment_reply_context: item?.attachment_reply_context || "",
        attachment_bundle: item?.attachment_bundle || {},
      };
      const out = await generateReply({
        email, analysis: { ...item }, force: false, user_id: userId,
        user_preferences: {
          availability_confirmation: answer,
          calendar_availability: calendarContext?.calendar_availability || item?.calendar_availability || null,
        },
      });
      const d = normalizeDraftPayload(out);
      const finalDecision = String(out?.decision || d?.decision || "").toUpperCase();
      const clarification = String(out?.clarification_question || d?.clarification_question || "");
      onPatchItem?.({
        reply_decision: finalDecision || item?.reply_decision,
        respond_recommended: Boolean(out?.respond_recommended ?? ["DRAFT_REPLY", "DRAFT_AND_ACTION"].includes(finalDecision)),
        clarification_question: clarification,
        reason: out?.reason || out?.understanding || item?.reason,
        ai_follow_up: out?.follow_up || item?.ai_follow_up || {},
        commitments: out?.commitments || item?.commitments || [],
        attachments: out?.attachments || item?.attachments || [],
        attachment_analysis: out?.attachment_analysis || item?.attachment_analysis || [],
        attachment_bundle: out?.attachment_bundle || item?.attachment_bundle || {},
        availability_confirmed_by_user: true,
        availability_confirmation: answer,
      });
      await persistSuggestedFollowup(out);
      if (["DRAFT_REPLY", "DRAFT_AND_ACTION"].includes(finalDecision)) {
        setDraft(d);
        setEditedText(d?.reply || "");
        setCalendarContext(null);
      } else {
        setDraft({ ...d, reply: "", safety_blocked: true, safety_reason: clarification || out?.reason || "More information is required." });
      }
    } catch (e) {
      setErr(String(e?.message || e));
    } finally {
      setAvailabilitySubmitting(false);
    }
  }

  async function onGenerateOrRegenerate() {
    setLoadingDraft(true);
    setErr("");

    try {
      const email = {
        id: item?.id,
        from: item?.from,
        subject: item?.subject,
        snippet: item?.snippet,
        body: item?.body || "",
        ts: item?.ts,
        provider: item?.provider || "gmail",
        threadId: item?.threadId || "",
        attachments: item?.attachments || [],
        attachment_analysis: item?.attachment_analysis || [],
        attachment_reply_context: item?.attachment_reply_context || "",
        attachment_bundle: item?.attachment_bundle || {},
      };

      const analysis = { ...item };

      const out = await generateReply({
        email,
        analysis,
        force: false,
        user_id: userId,
      });

      const d = normalizeDraftPayload(out);
      const finalDecision = String(out?.decision || d?.decision || "").toUpperCase();
      const finalReason = String(out?.reason || out?.understanding || d?.reason || "");
      const clarification = String(out?.clarification_question || d?.clarification_question || "");

      onPatchItem?.({
        reply_decision: finalDecision || item?.reply_decision,
        respond_recommended: Boolean(out?.respond_recommended ?? ["DRAFT_REPLY", "DRAFT_AND_ACTION"].includes(finalDecision)),
        clarification_question: clarification,
        reason: finalReason || item?.reason,
        ai_follow_up: out?.follow_up || item?.ai_follow_up || {},
        commitments: out?.commitments || item?.commitments || [],
        suggested_actions: out?.suggested_actions || item?.suggested_actions || [],
        attachments: out?.attachments || item?.attachments || [],
        attachment_analysis: out?.attachment_analysis || item?.attachment_analysis || [],
        attachment_bundle: out?.attachment_bundle || item?.attachment_bundle || {},
        attachment_reply_context: out?.attachment_bundle?.reply_context || item?.attachment_reply_context || "",
        calendar_checked: Boolean(out?.calendar_checked),
        calendar_availability: out?.calendar_availability || item?.calendar_availability || null,
      });

      await persistSuggestedFollowup(out);

      if (finalDecision === "ASK_USER" && out?.calendar_checked) {
        setCalendarContext(out);
      } else if (finalDecision !== "ASK_USER") {
        setCalendarContext(null);
      }

      if (["NO_REPLY", "ASK_USER", "ACTION_ONLY", "WAIT"].includes(finalDecision)) {
        setDraft({
          ...d,
          reply: "",
          safety_blocked: true,
          safety_reason: clarification || finalReason || "AI determined that a reply should not be drafted yet.",
          reply_meta: { ...(d?.reply_meta || {}), suppressed: true, decision: finalDecision },
        });
        setEditedText("");
      } else {
        setDraft(d);
        setEditedText(d?.reply || "");
      }
    } catch (e) {
      setErr(String(e?.message || e));
    } finally {
      setLoadingDraft(false);
    }
  }

  async function onGenerateMulti() {
    setLoadingMulti(true);
    setErr("");
    setMultiReplies([]);

    try {
      const res = await fetchMultiReply({
        email: {
          id: item?.id,
          from: item?.from,
          subject: item?.subject,
          snippet: item?.snippet,
          body: item?.body || "",
          ts: item?.ts,
          provider: item?.provider || "gmail",
          threadId: item?.threadId || "",
          attachments: item?.attachments || [],
          attachment_analysis: item?.attachment_analysis || [],
          attachment_reply_context: item?.attachment_reply_context || "",
          attachment_bundle: item?.attachment_bundle || {},
        },
        analysis: { ...item },
        user_id: userId,
      });

      setMultiReplies(Array.isArray(res?.options) ? res.options : []);
    } catch (e) {
      setErr(String(e?.message || e));
    } finally {
      setLoadingMulti(false);
    }
  }

  async function onSummarizeThread() {
    setLoadingSummary(true);
    setThreadSummary("");
    setErr("");

    try {
      if (!item?.threadId) {
        throw new Error("Missing threadId for this email.");
      }

      const res = await fetchThreadSummary(item.threadId, item?.provider || "gmail", item, userId);
      setThreadSummary(formatThreadSummary(res));
    } catch (e) {
      setErr(String(e?.message || e));
      setThreadSummary("Error generating summary");
    } finally {
      setLoadingSummary(false);
    }
  }

  async function onCreateFollowup() {
    setErr("");
    setFollowMsg("");

    try {
      await createFollowup({
        email_id: item?.id,
        thread_id: item?.threadId || "",
        remind_at: Number(item?.ai_follow_up?.remind_at_unix || 0) > Math.floor(Date.now() / 1000)
          ? Number(item.ai_follow_up.remind_at_unix)
          : Math.floor(Date.now() / 1000) + 3600,
        note: item?.ai_follow_up?.note || item?.ai_follow_up?.reason || "Follow up on this email",
        subject: item?.subject || "",
        sender: item?.from || "",
        provider: item?.provider || "gmail",
        user_id: userId,
      });
      setFollowMsg("Follow-up set");
      onFollowupCreated?.();
    } catch (e) {
      setErr(String(e?.message || e));
      setFollowMsg("Failed to set reminder");
    }
  }

  async function onCopy() {
    try {
      await navigator.clipboard.writeText(editing ? editedText : draft?.reply || "");
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      setErr("Copy failed.");
    }
  }

  if (!Badge) {
    return <div style={{ padding: 16, color: "crimson" }}>Badge import failed.</div>;
  }

  return (
    <article
      className={`emailCard redesign ${selected ? "selected" : ""} ${familyPersonal ? "familyHighlight" : ""} ${securityRelated ? "securityHighlight" : ""}`}
      onClick={onSelect}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect?.();
        }
      }}
    >
      <div className={`priorityRail ${priorityClass(item?.label)}`} />

      <div className="cardMain">
        <div className="cardTop">
          <div className="leftTop">
            <div className="subjectRow">
              <h3 className="subject">{subject}</h3>
              <Badge tone={badgeTone}>{item?.label}</Badge>
            </div>

            <div className="fromLine">{from}</div>
          </div>

          <div className="scoreStack">
            <div className={`scorePill ${priorityClass(item?.label)}`}>
              Priority {pct(item?.priority)}
            </div>
            <div className={`scorePill ${riskClass(item?.risk)}`}>
              Risk {pct(item?.risk)}
            </div>
          </div>
        </div>

        {preview && <p className="preview">{preview}</p>}

        {attachments.length > 0 && (
          <div className="attachmentRow" onClick={(e) => e.stopPropagation()}>
            {attachments.length > 1 && (
              <button className="softBtn" type="button" onClick={onAnalyzeAllAttachments} disabled={loadingAllAttachments}>
                {loadingAllAttachments ? "Summarizing all documents..." : `Summarize all ${attachments.length} documents`}
              </button>
            )}
            {attachments.map((att, idx) => {
              const key = String(att?.attachment_id || att?.filename || idx);
              const result = attachmentResults[key] || (item?.attachment_analysis || []).find((x) => x?.filename === att?.filename);
              const risky = ["medium", "high"].includes(String((result || att)?.risk_level || "").toLowerCase());
              const analyzed = Boolean(result);

              return (
                <div key={key} className={`attachmentChip ${risky ? "risky" : ""} ${analyzed ? "analyzed" : ""}`}>
                  <span>
                    {attachmentIcon(att?.file_type)} {shortFileName(att?.filename)}
                  </span>

                  <small>{attachmentDocLabel(att, result)}</small>

                  <button
                    className="microBtn"
                    type="button"
                    disabled={loadingAttachment === key}
                    onClick={() => onAnalyzeAttachment(att)}
                  >
                    {loadingAttachment === key ? "Summarizing..." : analyzed ? "✓ Summarized" : "Summarize"}
                  </button>

                  {result && (
                    <div className={`attachmentAnalysis ${result.risk_level || "low"}`}>
                      <div className="attachmentAnalysisHead">
                        <b>{result.document_label || "Document Intelligence"}</b>
                        {result.llm_summary_used ? <span>AI summary</span> : null}
                        {result.priority_boost ? <span>+{Math.round(Number(result.priority_boost) * 100)} priority</span> : null}
                      </div>

                      {result.title && <div className="attachmentDocTitle">{result.title}</div>}
                      <p>{result.summary}</p>

                      {result.business_value && (
                        <div className="attachmentBusinessValue">
                          <b>Why it matters:</b> {result.business_value}
                        </div>
                      )}

                      {(result.key_details || []).length > 0 && (
                        <div className="attachmentKeyDetails">
                          <b>Key details:</b>
                          {(result.key_details || []).map((x, i) => (
                            <div key={i}>• {x}</div>
                          ))}
                        </div>
                      )}

                      {(result.action_items || []).length > 0 && (
                        <div>
                          <b>Actions:</b>
                          {(result.action_items || []).map((x, i) => (
                            <div key={i}>• {x}</div>
                          ))}
                        </div>
                      )}

                      {(result.dates || []).length > 0 && (
                        <div><b>Dates:</b> {result.dates.join(", ")}</div>
                      )}

                      {(result.amounts || []).length > 0 && (
                        <div><b>Amounts:</b> {result.amounts.join(", ")}</div>
                      )}

                      {(result.ids || []).length > 0 && (
                        <div><b>IDs:</b> {result.ids.join(", ")}</div>
                      )}

                      {result.priority_reason && (
                        <div><b>Priority reason:</b> {result.priority_reason}</div>
                      )}

                      {(result.risk_reasons || []).length > 0 && (
                        <div>
                          <b>Risk:</b>
                          {(result.risk_reasons || []).map((x, i) => (
                            <div key={i}>• {x}</div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}


        <div className="tagRow">
          {familyPersonal && (
            <span className="glassTag signalIcon familySignal">👨‍👩‍👧 Family / Personal</span>
          )}

          {securityRelated && (
            <span className="glassTag signalIcon securitySignal">🔐 Security</span>
          )}

          {attachmentAnalyses.map((a, i) => (
            <span key={`${a?.filename || i}-${a?.document_type || "doc"}`} className={`glassTag attachmentType ${String(a?.document_type || "").toLowerCase()}`}>
              📎 {a?.document_label || a?.document_type || "Attachment"}
            </span>
          ))}

          <span className={`glassTag band ${String(item?.sender_band || "UNKNOWN").toLowerCase()}`}>
            {item?.sender_band || "UNKNOWN"}
          </span>

          <span className={`glassTag type ${senderType.toLowerCase()} ${familyPersonal ? "highlightIcon" : ""}`}>
            {senderTypeIcon(senderType)} {senderType}
          </span>

          {item?.source_folder && (
            <span className={`glassTag source ${String(item.source_folder).toLowerCase()}`}>
              {String(item.source_folder).toUpperCase()}
            </span>
          )}

          {item?.email_type && (
            <span className={`glassTag emailtype ${String(item.email_type).toLowerCase()}`}>
              {String(item.email_type).replaceAll("_", " ")}
            </span>
          )}

          {item?.relationship_type && (
            <span className={`glassTag relationship ${String(item.relationship_type).toLowerCase()}`}>
              {String(item.relationship_type).replaceAll("_", " ")}
            </span>
          )}

          {item?.intent && <span className="glassTag neutral">{item.intent}</span>}

          {showPref && (
            <span className={`glassTag pref ${userCat.toLowerCase()}`}>
              {icon(userCat)} {userCat}
            </span>
          )}
        </div>

        <div className="primaryActions" onClick={(e) => e.stopPropagation()}>
          <button className="softBtn" onClick={() => setOpen((v) => !v)} type="button">
            {open ? "Hide analysis" : "Show analysis"}
          </button>

          <button
            className="softBtn primary"
            onClick={onGenerateOrRegenerate}
            disabled={loadingDraft}
            title={!canReply && !replyNeedsFinalCheck ? noReplyReason(item) : "Let the Communication Brain understand the full message/thread and decide whether a reply is appropriate"}
            type="button"
          >
            {replyButtonLabel(item, loadingDraft, Boolean(draft))}
          </button>

          <button
            className="softBtn"
            onClick={onGenerateMulti}
            disabled={loadingMulti || !canReply}
            title={!canReply ? noReplyReason(item) : "Generate multiple reply options"}
            type="button"
          >
            {loadingMulti ? "Generating..." : "Multi Reply"}
          </button>

          <button
            className="softBtn"
            onClick={onSummarizeThread}
            disabled={loadingSummary}
            type="button"
          >
            {loadingSummary ? "Summarizing..." : "Summarize Thread"}
          </button>

          <button
            className="softBtn"
            onClick={onCreateFollowup}
            type="button"
          >
            Follow-up
          </button>

          {draft && !draft.safety_blocked && (
            <button className="softBtn" onClick={onCopy} type="button">
              {copied ? "Copied" : "Copy"}
            </button>
          )}
        </div>

        <div className="feedbackRow" onClick={(e) => e.stopPropagation()}>
          <button className="microBtn" onClick={() => onFeedback("IMPORTANT")} type="button">
            ⭐ Important
          </button>
          <button className="microBtn" onClick={() => onFeedback("LESS")} type="button">
            🕓 Less
          </button>
          <button className="microBtn" onClick={() => onFeedback("SPAM")} type="button">
            🚫 Spam
          </button>
          <button className="microBtn" onClick={() => onFeedback("PROMO")} type="button">
            🏷️ Promo
          </button>
        </div>

        {calendarContext && String(calendarContext?.clarification_question || "").trim() && (
          <div className="notice schedulingQuestion" onClick={(e) => e.stopPropagation()}>
            <b>Calendar checked</b>
            {calendarContext?.requested_time?.event_at_unix && (
              <div className="scheduleTime">Requested time: {new Date(Number(calendarContext.requested_time.event_at_unix) * 1000).toLocaleString()} {calendarContext?.requested_time?.timezone_label || ""}</div>
            )}
            <div>{calendarContext.clarification_question}</div>
            <div className="primaryActions">
              <button className="softBtn primary" type="button" disabled={availabilitySubmitting} onClick={() => submitAvailabilityConfirmation("yes")}>
                {availabilitySubmitting ? "Working..." : "Yes, I’m available"}
              </button>
              <button className="softBtn" type="button" disabled={availabilitySubmitting} onClick={() => submitAvailabilityConfirmation("no")}>
                No, I’m not available
              </button>
            </div>
          </div>
        )}
        {!canReply && !replyNeedsFinalCheck && <div className="notice subtleNotice">{noReplyReason(item)}</div>}
        {savedMsg && <div className="notice">{savedMsg}</div>}
        {followMsg && <div className="notice">{followMsg}</div>}
        {gmailDraftMsg && <div className="notice">{gmailDraftMsg}</div>}
        {item?.ai_follow_up?.needed && (
          <div className="notice">AI follow-up: {item.ai_follow_up.reason || item.ai_follow_up.note || "A reminder is recommended."}</div>
        )}
        {(item?.commitments || []).length > 0 && (
          <div className="notice">Commitments detected: {(item.commitments || []).map((x) => typeof x === "string" ? x : (x?.text || x?.commitment || JSON.stringify(x))).join("; ")}</div>
        )}
        {err && <div className="error">{err}</div>}

        {open && (
          <div className="analysisPanel" onClick={(e) => e.stopPropagation()}>
            <div className="analysisGrid">
              <div className="analysisBox">
                <span>Priority</span>
                <strong>{pct(item?.priority)}</strong>
              </div>

              <div className="analysisBox">
                <span>Risk</span>
                <strong>{pct(item?.risk)}</strong>
              </div>

              <div className="analysisBox">
                <span>Sender Band</span>
                <strong>{item?.sender_band || "UNKNOWN"}</strong>
              </div>

              <div className="analysisBox">
                <span>Intent</span>
                <strong>{item?.intent || "Unknown"}</strong>
              </div>
            </div>

            <div className="reasonBox">
              <div className="sectionLabel">Why this matters</div>
              <div className="reasonText">{item?.reason || "No explanation available."}</div>
            </div>

            {attachmentAnalyses.length > 0 && (
              <div className="reasonBox">
                <div className="sectionLabel">Attachment Intelligence</div>
                <div className="reasonText attachmentPanelText">
                  {attachmentAnalyses.map((a, i) => (
                    <div key={`${a?.filename || i}-panel`} className="attachmentPanelItem">
                      <b>{a?.document_label || "Attachment"}</b> — {a?.filename}
                      {a?.priority_boost ? <span> • priority boost +{Math.round(Number(a.priority_boost) * 100)}</span> : null}
                      {a?.llm_summary_used ? <span> • AI summary</span> : null}
                      {a?.title ? <div><b>Title:</b> {a.title}</div> : null}
                      <div>{a?.summary || "No attachment summary available."}</div>
                      {a?.business_value ? <div><b>Why it matters:</b> {a.business_value}</div> : null}
                      {(a?.key_details || []).length > 0 && (
                        <div>Key details: {(a.key_details || []).join("; ")}</div>
                      )}
                      {(a?.action_items || []).length > 0 && (
                        <div>Actions: {(a.action_items || []).join("; ")}</div>
                      )}
                      {(a?.ids || []).length > 0 && (
                        <div>IDs: {(a.ids || []).join("; ")}</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}


            {item?.attachment_bundle?.summary && (
              <div className="reasonBox">
                <div className="sectionLabel">Combined Document Understanding</div>
                <div className="reasonText">
                  <div>{item.attachment_bundle.summary}</div>
                  {(item.attachment_bundle.key_facts || []).length > 0 && (
                    <div><b>Cross-document facts:</b> {(item.attachment_bundle.key_facts || []).join("; ")}</div>
                  )}
                  {(item.attachment_bundle.conflicts || []).length > 0 && (
                    <div><b>Conflicts:</b> {(item.attachment_bundle.conflicts || []).join("; ")}</div>
                  )}
                  {(item.attachment_bundle.action_items || []).length > 0 && (
                    <div><b>Combined actions:</b> {(item.attachment_bundle.action_items || []).join("; ")}</div>
                  )}
                </div>
              </div>
            )}

            <div className="reasonBox">
              <div className="sectionLabel">Risk Explanation</div>
              <div className="reasonText">
                {(item?.risk_reasons || item?.human_signals?.risk_reasons || []).length
                  ? (item?.risk_reasons || item?.human_signals?.risk_reasons || []).map((x, i) => <div key={i}>• {x}</div>)
                  : "No major risk signals detected."}
              </div>
            </div>
          </div>
        )}

        {threadSummary && (
          <div className="analysisPanel" onClick={(e) => e.stopPropagation()}>
            <div className="sectionLabel">Thread Summary</div>
            <div className="reasonText" style={{ whiteSpace: "pre-wrap" }}>
              {threadSummary}
            </div>
          </div>
        )}

        {multiReplies.length > 0 && (
          <div className="analysisPanel" onClick={(e) => e.stopPropagation()}>
            <div className="sectionLabel">Multi Reply Options</div>
            <div className="reasonText" style={{ whiteSpace: "pre-wrap" }}>
              {multiReplies.map((r, i) => `${i + 1}. ${r}`).join("\n\n")}
            </div>
          </div>
        )}

        {draft && (
          <div className="draftShell" onClick={(e) => e.stopPropagation()}>
            {draft.safety_blocked ? (
              <div className="muted">
                <b>
                  {String(draft?.decision || draft?.reply_meta?.decision || "").toUpperCase() === "NO_REPLY"
                    ? "No reply recommended:"
                    : String(draft?.decision || draft?.reply_meta?.decision || "").toUpperCase() === "ASK_USER"
                      ? "Need your input:"
                      : "Draft paused:"}
                </b>{" "}
                {draft.safety_reason}
              </div>
            ) : (
              <>
                <div className="draftTop">
                  <div>
                    <div className="draftTitle">Suggested Reply</div>
                    <div className="draftMeta">
                      tone: {draft.tone} • conf: {Math.round((draft.confidence || 0) * 100)}%
                    </div>
                  </div>

                  <div className="draftActionRow">
                    <button
                      className="softBtn"
                      onClick={() => {
                        setEditing((v) => !v);
                        setEditedText(draft?.reply || "");
                      }}
                      type="button"
                    >
                      {editing ? "Cancel" : "Edit"}
                    </button>

                    <button
                      className="softBtn"
                      onClick={() => onSaveExample(false)}
                      disabled={savingExample}
                      type="button"
                    >
                      {savingExample ? "Saving..." : "Use this"}
                    </button>

                    <button
                      className="softBtn primary"
                      onClick={onCreateGmailDraft}
                      disabled={creatingGmailDraft || !draft?.reply}
                      type="button"
                      title="Create a Gmail draft inside the original conversation thread"
                    >
                      {creatingGmailDraft ? "Saving draft..." : "Save to Gmail thread"}
                    </button>

                    {editing && (
                      <button
                        className="softBtn primary"
                        onClick={() => onSaveExample(true)}
                        disabled={savingExample}
                        type="button"
                      >
                        {savingExample ? "Saving..." : "Save edited"}
                      </button>
                    )}
                  </div>
                </div>

                {editing ? (
                  <textarea
                    className="draftEdit"
                    value={editedText}
                    onChange={(e) => setEditedText(e.target.value)}
                  />
                ) : (
                  <pre className="draftText">{String(draft.reply || "")}</pre>
                )}

                {draft.reply_meta && (
                  <div className="draftFoot">
                    {draft.reply_meta.regenerated !== undefined ? `regen: ${draft.reply_meta.regenerated ? "yes" : "no"}` : ""}
                    {draft.reply_meta.used_rag !== undefined ? ` • used_rag: ${String(draft.reply_meta.used_rag)}` : ""}
                    {draft.reply_meta.suppressed !== undefined ? ` • suppressed: ${String(draft.reply_meta.suppressed)}` : ""}
                    {draft.reply_meta.reply_intent ? ` • intent: ${draft.reply_meta.reply_intent}` : ""}
                    {draft.reply_meta.strategy ? ` • strategy: ${draft.reply_meta.strategy}` : ""}
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </article>
  );
}