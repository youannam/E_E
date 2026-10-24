import { useState } from "react";

import { api } from "../api/client";
import type { ModelStatus, Rule } from "../api/types";
import { useApi } from "../api/useApi";
import { useAuth } from "../auth/AuthContext";
import { SeverityText } from "../components/Badges";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DataState } from "../components/DataState";
import { PageHeader } from "../components/Layout";
import { formatDateTime, humanize } from "../utils/format";

interface PendingChange {
  rule: Rule;
  body: Record<string, unknown>;
  description: string;
}

/** Only plain numeric parameters are editable here; role clearances are shown read-only. */
function numericParameters(rule: Rule): [string, number][] {
  return Object.entries(rule.parameters).filter((entry): entry is [string, number] => typeof entry[1] === "number");
}

export function RulesPage() {
  const { account } = useAuth();
  const isAdmin = account?.role === "ADMIN";
  const rules = useApi<Rule[]>("/rules");
  const model = useApi<ModelStatus>("/models/status");
  const [drafts, setDrafts] = useState<Record<string, Record<string, string>>>({});
  const [pending, setPending] = useState<PendingChange | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function draftValue(rule: Rule, key: string, current: number): string {
    return drafts[rule.rule_id]?.[key] ?? String(current);
  }

  function setDraft(rule: Rule, key: string, value: string) {
    setDrafts((old) => ({ ...old, [rule.rule_id]: { ...old[rule.rule_id], [key]: value } }));
  }

  function prepareSave(rule: Rule) {
    const draft = drafts[rule.rule_id] ?? {};
    const parameters: Record<string, number> = {};
    let weight: number | undefined;
    for (const [key, text] of Object.entries(draft)) {
      const value = Number(text);
      if (text.trim() === "" || Number.isNaN(value) || value < 0) {
        setError(`${humanize(key)} must be a number of zero or more.`);
        return;
      }
      if (key === "weight") weight = value;
      else parameters[key] = value;
    }
    setError(null);
    const body: Record<string, unknown> = {};
    if (weight !== undefined) body.weight = weight;
    if (Object.keys(parameters).length) body.parameters = parameters;
    if (!Object.keys(body).length) return;
    setPending({ rule, body, description: `Save the new settings for "${rule.name}"? They apply to every analysis from now on.` });
  }

  async function confirm() {
    if (!pending) return;
    setSaving(true);
    try {
      await api.patch<Rule>(`/rules/${pending.rule.rule_id}`, pending.body);
      setDrafts((old) => ({ ...old, [pending.rule.rule_id]: {} }));
      setMessage(`Saved "${pending.rule.name}".`);
      rules.reload();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
      setPending(null);
    }
  }

  const metrics = model.data?.metrics as { test_period_ai_only?: Record<string, number> } | undefined;
  const aiMetrics = metrics?.test_period_ai_only;

  return (
    <>
      <PageHeader title="Detection rules" subtitle="Explicit cybersecurity rules, and the AI model they work alongside." />
      {message && <p className="form-success" role="status">{message}</p>}
      {error && <p className="form-error" role="alert">{error}</p>}

      <section className="panel">
        <h2>AI anomaly model</h2>
        <DataState loading={model.loading} error={model.error}>
          {model.data && (
            model.data.loaded ? (
              <dl className="facts facts-inline">
                <div><dt>Version</dt><dd>{model.data.version}</dd></div>
                <div><dt>Trained</dt><dd>{formatDateTime(model.data.trained_at)}</dd></div>
                <div><dt>Features</dt><dd>{model.data.feature_names.length}</dd></div>
                {aiMetrics && (
                  <div><dt>Synthetic test set</dt>
                    <dd>precision {aiMetrics.precision}, recall {aiMetrics.recall}, false-positive rate {aiMetrics.false_positive_rate}</dd></div>
                )}
              </dl>
            ) : <p className="form-notice">{model.data.message}</p>
          )}
        </DataState>
      </section>

      <DataState loading={rules.loading && !rules.data} error={rules.error} onRetry={rules.reload}>
        <div className="rules">
          {rules.data?.map((rule) => (
            <section key={rule.rule_id} className={`panel rule ${rule.enabled ? "" : "rule-disabled"}`}>
              <div className="finding-head">
                <h2>{rule.name}</h2>
                <SeverityText severity={rule.severity} />
                <span className="muted">{rule.enabled ? "Enabled" : "Disabled"}</span>
              </div>
              <p>{rule.description}</p>
              <p className="muted small">Rule ID {rule.rule_id}. Window: {rule.time_window}. Needs: {rule.required_fields.join(", ")}.</p>

              <div className="rule-settings">
                <label>
                  Weight (points)
                  <input type="number" min={0} max={100} disabled={!isAdmin} value={draftValue(rule, "weight", rule.weight)}
                         onChange={(e) => setDraft(rule, "weight", e.target.value)} />
                </label>
                {numericParameters(rule).map(([key, value]) => (
                  <label key={key}>
                    {humanize(key)}
                    <input type="number" min={0} step="any" disabled={!isAdmin} value={draftValue(rule, key, value)}
                           onChange={(e) => setDraft(rule, key, e.target.value)} />
                  </label>
                ))}
              </div>
              {"role_clearance" in rule.parameters && (
                <details>
                  <summary>Role clearances</summary>
                  <ul className="simple-list">
                    {Object.entries(rule.parameters.role_clearance as Record<string, string>).map(([role, level]) => (
                      <li key={role}>{role}: {humanize(level)}</li>
                    ))}
                  </ul>
                </details>
              )}
              {isAdmin && (
                <div className="action-buttons">
                  <button className="button" onClick={() => prepareSave(rule)}
                          disabled={!Object.keys(drafts[rule.rule_id] ?? {}).length}>
                    Save settings
                  </button>
                  <button className="button button-secondary"
                          onClick={() => setPending({ rule, body: { enabled: !rule.enabled },
                            description: `${rule.enabled ? "Disable" : "Enable"} "${rule.name}"? This changes all future analyses.` })}>
                    {rule.enabled ? "Disable rule" : "Enable rule"}
                  </button>
                </div>
              )}
            </section>
          ))}
        </div>
      </DataState>

      {pending && (
        <ConfirmDialog title="Change detection rule" message={pending.description} confirmLabel="Save change" busy={saving}
                       onCancel={() => setPending(null)} onConfirm={confirm} />
      )}
    </>
  );
}
