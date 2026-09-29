function fmtEvent(item) {
  const t = Number(item?.grounded_timing?.event_at || item?.requested_time?.event_at_unix || 0);
  return t ? new Date(t * 1000).toLocaleString() : "";
}

export default function DetailPanel({ item }) {
  if (!item) return (
    <aside className="detailPane"><div className="detailEmpty">
      <div className="detailEmptyTitle">Select an email</div>
      <div className="detailEmptySub">Email-AI will show what matters and what you can do next.</div>
    </div></aside>
  );
  const reply=item?.suggested_reply ?? item?.reply?.text ?? item?.reply?.reply ?? item?.reply ?? "";
  const event=fmtEvent(item);
  const risks=item?.risk_reasons || item?.human_signals?.risk_reasons || [];
  const majorRisk=Number(item?.risk||0)>=0.6;
  return (
    <aside className="detailPane">
      <div className="paneHeader sticky"><div><div className="paneTitle">Email Intelligence</div><div className="paneSub">What matters and what to do next</div></div></div>
      <div className="detailBody">
        <div className="detailCard"><div className="detailSubject">{item?.subject||"(no subject)"}</div><div className="detailFrom">{item?.from||"(no sender)"}</div>{event&&<div className="detailText"><b>When:</b> {event}</div>}</div>
        <div className="detailCard"><div className="detailLabel">What you need to know</div><p className="detailText">{item?.reason||"No explanation available yet."}</p></div>
        <div className="detailCard"><div className="detailLabel">Recommended action</div><p className="detailText">{item?.respond_recommended?"A response is recommended.":item?.requires_action?"Action is required; a reply may not be necessary.":"No immediate action detected."}</p></div>
        {majorRisk&&<div className="detailCard"><div className="detailLabel">Security warning</div><ul className="detailList">{risks.slice(0,4).map((x,i)=><li key={i}>{x}</li>)}</ul></div>}
        {(item?.attachments||[]).length>0&&<details className="detailCard"><summary>Attachments ({item.attachments.length})</summary><div className="detailText">{(item.attachment_analysis||[]).map((a,i)=><div key={i}><b>{a?.document_label||"Attachment"}</b>{a?.summary?` — ${a.summary}`:""}</div>)}</div></details>}
        <details className="detailCard"><summary>Original email</summary><p className="detailText">{item?.snippet||"No preview available."}</p></details>
        {reply&&<div className="detailCard"><div className="detailLabel">Suggested reply</div><div className="replyPreview">{reply}</div></div>}
        <details className="detailCard"><summary>Technical details</summary><div className="detailText">Priority {Math.round(Number(item?.priority||0)*100)}% · Risk {Math.round(Number(item?.risk||0)*100)}% · {item?.intent||"Unknown intent"} · {item?.sender_band||"Unknown sender"}</div></details>
      </div>
    </aside>
  );
}
