import { useState } from "react";

import { api } from "../api/client";
import type { AlertDetail, AlertStatus } from "../api/types";
import { useApi } from "../api/useApi";
import { useAuth } from "../auth/AuthContext";
import { RiskBadge, SensitivityText, SeverityText, SimulatedTag, StatusBadge } from "../components/Badges";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DataState } from "../components/DataState";
import { PageHeader } from "../components/Layout";
import { RiskBreakdown } from "../components/RiskBreakdown";
import { formatBytes, formatDateTime, formatScore, formatTime, humanize } from "../utils/format";

// What an analyst can move an alert to, from each status.
const NEXT_STATUSES: Record<AlertStatus, AlertStatus[]> = {
  OPEN: ["INVESTIGATING", "RESOLVED", "FALSE_POSITIVE"],
  INVESTIGATING: ["RESOLVED", "FALSE_POSITIVE", "OPEN"],
  RESOLVED: ["OPEN"],
  FALSE_POSITIVE: ["OPEN"],
};
const ACTION_LABELS: Record<AlertStatus, string> = {
  OPEN: "Reopen",
  INVESTIGATING: "Start investigating",
  RESOLVED: "Mark resolved",
  FALSE_POSITIVE: "Mark false positive",
};

export function AlertDetailPage({ alertId }: { alertId: number }) {
  const { account } = useAuth();
  const isAdmin = account?.role === "ADMIN";
  const { data: alert, loading, error, reload, setData } = useApi<AlertDetail>(`/alerts/${alertId}`);
  const [note, setNote] = useState("");
  const [pendingStatus, setPendingStatus] = useState<AlertStatus | null>(null);
  const [saving, setSaving] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [responseActions, setResponseActions] = useState<Array<{id:string;title:string;description:string}>>([]);

  async function runResponseAction(actionId: string) {
    setSaving(true); setActionError(null); setMessage(null);
    try { await api.post(`/alerts/${alertId}/response-actions/${actionId}`, {}); const data=await api.get<{actions:Array<{id:string;title:string;description:string}>}>(`/alerts/${alertId}/response-actions`); setResponseActions(data.actions); await reload(); setMessage("Response action recorded in alert history."); }
    catch(err) { setActionError((err as Error).message); } finally { setSaving(false); }
  }
  async function loadResponseActions() { try { const data=await api.get<{actions:Array<{id:string;title:string;description:string}>}>(`/alerts/${alertId}/response-actions`); setResponseActions(data.actions); } catch { /* main alert error state remains authoritative */ } }
  async function save(body: Record<string, unknown>, done: string) {
    setSaving(true);
    setActionError(null);
    try {
      const updated = await api.patch<AlertDetail>(`/alerts/${alertId}`, body);
      setData(updated);
      setNote("");
      setMessage(done);
    } catch (err) {
      setActionError((err as Error).message);
    } finally {
      setSaving(false);
      setPendingStatus(null);
    }
  }

  function requestStatus(status: AlertStatus) {
    setMessage(null);
    if ((status === "RESOLVED" || status === "FALSE_POSITIVE") && !note.trim()) {
      setActionError("Write a note explaining the decision before closing the alert.");
      return;
    }
    setActionError(null);
    setPendingStatus(status);
  }

  return (
    <>
      <p className="breadcrumb"><a href="#/alerts">Alerts</a> / Alert #{alertId}</p>
      <DataState loading={loading && !alert} error={error} onRetry={reload}>
        {alert && (
          <>
            <PageHeader
              title={`${alert.username} on ${alert.window_date}`}
              subtitle={<>{alert.user.job_role}, {alert.user.department}. Raised {formatDateTime(alert.created_at)}
                {alert.occurrence_count > 1 && `, updated by ${alert.occurrence_count - 1} later analyses`}.</>}
              actions={<><RiskBadge level={alert.risk_level} score={alert.risk_score} /><StatusBadge status={alert.status} /></>}
            />

            <div className="grid-detail">
              <div className="stack">
                {alert.analysis && <RiskBreakdown analysis={alert.analysis} />}

                <section className="panel">
                  <h2>Cybersecurity rules ({alert.triggered_rules.length})</h2>
                  {alert.triggered_rules.length === 0 ? (
                    <p className="muted">No rule fired. This alert comes from the AI anomaly score alone.</p>
                  ) : (
                    <ul className="findings">
                      {alert.triggered_rules.map((rule) => (
                        <li key={rule.rule_id}>
                          <div className="finding-head">
                            <strong>{rule.name}</strong>
                            <SeverityText severity={rule.severity} />
                            <span className="muted">+{formatScore(rule.contribution)} points</span>
                          </div>
                          <p>{rule.reason}</p>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>

                <section className="panel">
                  <h2>AI anomaly model</h2>
                  {alert.ai_status === "OK" ? (
                    <dl className="facts">
                      <div><dt>Anomaly score</dt><dd>{formatScore(alert.ai_score)} / 100</dd></div>
                      <div><dt>Model verdict</dt>
                        <dd>{alert.ai_is_anomaly ? "Unusual compared with normal training days" : "Within normal variation"}</dd></div>
                      <div><dt>Model version</dt><dd>{alert.model_version}</dd></div>
                      <div><dt>Baseline used</dt><dd>{humanize(alert.analysis?.baseline_type ?? "unknown")}</dd></div>
                    </dl>
                  ) : (
                    <p className="muted">The AI model was not available; this score uses rules only.</p>
                  )}
                  <p className="panel-note">
                    The anomaly score says how different this day is from normal days; it is not a probability that
                    the person acted maliciously.
                  </p>
                </section>

                <section className="panel">
                  <h2>Explanation</h2>
                  <p className="explanation">{alert.explanation}</p>
                </section>

                <section className="panel">
                  <h2>Evidence timeline ({alert.activities.length} events)</h2>
                  <ol className="timeline">
                    {alert.activities.map((activity) => (
                      <li key={activity.id}>
                        <time>{formatTime(activity.timestamp)}</time>
                        <span className="timeline-type">{humanize(activity.event_type)}</span>
                        <span className="timeline-resource">{activity.resource ?? activity.device_id ?? ""}</span>
                        <SensitivityText value={activity.sensitivity} />
                        <span className="muted">{activity.file_size_bytes ? formatBytes(activity.file_size_bytes) : ""}</span>
                        {activity.is_simulated && <SimulatedTag />}
                      </li>
                    ))}
                  </ol>
                </section>
              </div>

              <aside className="stack">
                <section className="panel">
                  <h2>Recommended response actions</h2>
                  <p className="muted small">Actions are selected from alert evidence and risk level. Execution is checked by the backend and recorded in history.</p>
                  <button className="button button-secondary" onClick={loadResponseActions}>Load recommended actions</button>
                  {responseActions.map(action => <div className="response-action" key={action.id}><strong>{action.title}</strong><p>{action.description}</p><button className="button" disabled={saving} onClick={()=>runResponseAction(action.id)}>Run action</button></div>)}
                </section>
                <section className="panel">
                  <h2>Investigation</h2>
                  <p className="muted small">
                    Assigned to: {alert.assigned_to ?? "nobody"}
                    {alert.resolution_notes && <><br />Resolution: {alert.resolution_notes}</>}
                  </p>
                  <label htmlFor="note">Analyst note</label>
                  <textarea id="note" rows={4} value={note} maxLength={2000} onChange={(e) => setNote(e.target.value)}
                            placeholder="What did you check? What did you decide and why?" />
                  <div className="action-buttons">
                    {NEXT_STATUSES[alert.status].map((status) => (
                      <button key={status} className="button" disabled={saving} onClick={() => requestStatus(status)}>
                        {ACTION_LABELS[status]}
                      </button>
                    ))}
                    <button className="button button-secondary" disabled={saving || !note.trim()}
                            onClick={() => save({ note }, "Note added.")}>
                      Add note
                    </button>
                    <button className="button button-secondary" disabled={saving}
                            onClick={() => save({ assign_to_me: !alert.assigned_to }, alert.assigned_to ? "Unassigned." : "Assigned to you.")}>
                      {alert.assigned_to ? "Unassign" : "Assign to me"}
                    </button>
                  </div>
                  {actionError && <p className="form-error" role="alert">{actionError}</p>}
                  {message && <p className="form-success" role="status">{message}</p>}
                </section>

                <section className="panel">
                  <h2>Status history</h2>
                  <ol className="history">
                    {alert.history.map((entry) => (
                      <li key={entry.id}>
                        <strong>{humanize(entry.action)}</strong>
                        {entry.new_status && <> → {humanize(entry.new_status)}</>}
                        <div className="muted small">By {entry.actor}, {formatDateTime(entry.created_at)}</div>
                        {entry.note && <p>{entry.note}</p>}
                      </li>
                    ))}
                  </ol>
                </section>

                <section className="panel">
                  <h2>User</h2>
                  <dl className="facts">
                    <div><dt>Username</dt><dd>{isAdmin ? <a href={`#/users/${alert.user.id}`}>{alert.user.username}</a> : alert.user.username}</dd></div>
                    <div><dt>Current risk</dt><dd><RiskBadge level={alert.user.current_risk_level} score={alert.user.current_risk_score} /></dd></div>
                    <div><dt>Alerts</dt><dd>{alert.user.alert_count} total, {alert.user.open_alert_count} open</dd></div>
                  </dl>
                </section>
              </aside>
            </div>

            {pendingStatus && (
              <ConfirmDialog
                title={ACTION_LABELS[pendingStatus]}
                message={`Change alert #${alert.id} from ${humanize(alert.status)} to ${humanize(pendingStatus)}? This is recorded in the status history.`}
                confirmLabel={ACTION_LABELS[pendingStatus]}
                busy={saving}
                onCancel={() => setPendingStatus(null)}
                onConfirm={() => save({ status: pendingStatus, note: note.trim() || undefined },
                                      `Status changed to ${humanize(pendingStatus)}.`)}
              />
            )}
          </>
        )}
      </DataState>
    </>
  );
}
