import { useState, type FormEvent } from "react";

import { api } from "../api/client";
import type { Scenario, SimulationResponse } from "../api/types";
import { useApi } from "../api/useApi";
import { useAuth } from "../auth/AuthContext";
import { RiskBadge, SensitivityText, SeverityText, SimulatedTag } from "../components/Badges";
import { DataState } from "../components/DataState";
import { PageHeader } from "../components/Layout";
import { RiskBreakdown } from "../components/RiskBreakdown";
import { formatBytes, formatScore, formatTime, humanize, yesterdayIso } from "../utils/format";

export function SimulationPage() {
  const { account } = useAuth();
  const canDetect = account?.role === "ADMIN" || account?.role === "ANALYST";
  const scenarios = useApi<Scenario[]>("/simulator/scenarios");
  const users = useApi<{ id: number; username: string; job_role: string; department: string }[]>("/simulator/targets");

  const [scenarioId, setScenarioId] = useState("COMBINED_ANOMALY");
  const [userId, setUserId] = useState("");
  const [date, setDate] = useState(yesterdayIso());
  const [seed, setSeed] = useState(42);
  const [intensity, setIntensity] = useState(1);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SimulationResponse | null>(null);

  async function run(event: FormEvent) {
    event.preventDefault();
    if (!userId) {
      setError("Choose the user to simulate.");
      return;
    }
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const response = await api.post<SimulationResponse>("/simulator/run", {
        scenario_id: scenarioId, user_id: Number(userId), date, seed, intensity,
      });
      setResult(response);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRunning(false);
    }
  }

  const analysis = result?.analysis;

  return (
    <>
      <PageHeader
        title="Detection Lab"
        subtitle="Test detection rules and AI analysis with sample activity."
      />

      <p className="form-notice">Sample activity is generated for testing. Each run passes through the detection rules, AI scoring, and alert pipeline.</p>

      <form className="simulation" onSubmit={run}>
        <fieldset className="panel">
          <legend>1. Choose a scenario</legend>
          <DataState loading={scenarios.loading} error={scenarios.error} onRetry={scenarios.reload}>
            <div className="scenario-list" role="radiogroup">
              {scenarios.data?.map((scenario) => (
                <label key={scenario.id} className={`scenario ${scenarioId === scenario.id ? "selected" : ""}`}>
                  <input type="radio" name="scenario" value={scenario.id} checked={scenarioId === scenario.id}
                         onChange={() => setScenarioId(scenario.id)} />
                  <span>
                    <strong>{scenario.name}</strong>
                    <span className={scenario.suspicious ? "tag-suspicious" : "tag-benign"}>
                      {scenario.suspicious ? "suspicious" : "legitimate"}
                    </span>
                    <span className="muted">{scenario.description}</span>
                    <span className="small">Expect: {scenario.expected_signals.join("; ")}</span>
                  </span>
                </label>
              ))}
            </div>
          </DataState>
        </fieldset>

        <fieldset className="panel sim-params">
          <legend>2. Set the parameters</legend>
          <label>
            User
            <select value={userId} onChange={(e) => setUserId(e.target.value)} required>
              <option value="">Choose a user…</option>
              {users.data?.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.username} ({user.department} · {user.job_role})
                </option>
              ))}
            </select>
          </label>
          <label>
            Day to simulate
            <input type="date" value={date} max={new Date().toISOString().slice(0, 10)} onChange={(e) => setDate(e.target.value)} />
          </label>
          <label>
            Random seed
            <input type="number" min={0} max={1000000} value={seed} onChange={(e) => setSeed(Number(e.target.value))} />
          </label>
          <label>
            Intensity
            <select value={intensity} onChange={(e) => setIntensity(Number(e.target.value))}>
              <option value={1}>1 (mild)</option>
              <option value={2}>2</option>
              <option value={3}>3 (strong)</option>
            </select>
          </label>
          <p className="panel-note">
            The same user, day, seed and intensity always generate the same events. Events are added to that
            day, so to see a scenario on its own pick a day without other activity for this user (the default,
            yesterday, is kept free by the demo data).
          </p>
          <button className="button button-wide" type="submit" disabled={!canDetect || running}>
            {running ? "Running the pipeline…" : "Run simulation"}
          </button>
          {error && <p className="form-error" role="alert">{error}</p>}
        </fieldset>
      </form>

      {result && (
        <section className="result" aria-live="polite">
          <h2>
            3. Result: {result.events_created} simulated events for {result.date}
          </h2>
          {analysis && (
            <div className="grid-detail">
              <div className="stack">
                <RiskBreakdown analysis={analysis} />
                <section className="panel">
                  <h2>Rules triggered ({analysis.triggered_rules.length})</h2>
                  {analysis.triggered_rules.length === 0 ? (
                    <p className="muted">No cybersecurity rule fired.</p>
                  ) : (
                    <ul className="findings">
                      {analysis.triggered_rules.map((rule) => (
                        <li key={rule.rule_id}>
                          <div className="finding-head">
                            <strong>{rule.name}</strong>
                            <SeverityText severity={rule.severity} />
                            <span className="muted">+{formatScore(rule.contribution)}</span>
                          </div>
                          <p>{rule.reason}</p>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              </div>
              <aside className="stack">
                <section className="panel">
                  <h2>Outcome</h2>
                  <dl className="facts">
                    <div><dt>Baseline</dt><dd>{humanize(analysis.baseline_type)}</dd></div>
                    <div><dt>AI anomaly score</dt>
                      <dd>{analysis.ai_status === "OK" ? `${formatScore(analysis.ai_score)} (${analysis.ai_is_anomaly ? "anomalous" : "normal range"})` : "model unavailable"}</dd></div>
                    <div><dt>Events that day</dt><dd>{analysis.event_count}</dd></div>
                    <div><dt>Alert</dt>
                      <dd>{result.alert ? (
                        <a href={`#/alerts/${result.alert.id}`}>
                          Alert #{result.alert.id} <RiskBadge level={result.alert.risk_level} />
                        </a>
                      ) : "No alert: the score is below the alert threshold"}</dd></div>
                  </dl>
                </section>
              </aside>
            </div>
          )}

          <section className="panel">
            <h2>Generated events</h2>
            <table className="table table-compact">
              <thead>
                <tr><th>Time</th><th>Event</th><th>Resource</th><th>Sensitivity</th><th>Size</th><th /></tr>
              </thead>
              <tbody>
                {result.activities.map((activity) => (
                  <tr key={activity.id}>
                    <td className="nowrap">{formatTime(activity.timestamp)}</td>
                    <td>{humanize(activity.event_type)}</td>
                    <td className="truncate">{activity.resource ?? activity.device_id ?? ""}</td>
                    <td><SensitivityText value={activity.sensitivity} /></td>
                    <td>{activity.file_size_bytes ? formatBytes(activity.file_size_bytes) : ""}</td>
                    <td><SimulatedTag /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </section>
      )}
    </>
  );
}
