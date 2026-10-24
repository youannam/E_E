import { useApi } from "../api/useApi";
import type {
  AlertSummary,
  AlertsOverTimeItem,
  DashboardSummary,
  Page,
  RiskLevel,
} from "../api/types";
import { RISK_LEVELS } from "../api/types";
import { RiskBadge, StatusBadge } from "../components/Badges";
import { ColumnChart } from "../components/charts/ColumnChart";
import { HorizontalBars } from "../components/charts/HorizontalBars";
import { DataState } from "../components/DataState";
import { PageHeader } from "../components/Layout";
import { formatDateTime, humanize, RISK_COLORS } from "../utils/format";
import { navigate } from "../utils/router";

export function DashboardPage() {
  const summary = useApi<DashboardSummary>("/dashboard/summary");
  const overTime = useApi<AlertsOverTimeItem[]>("/dashboard/alerts-over-time?days=14");
  const risk = useApi<{ level: RiskLevel; count: number }[]>("/dashboard/risk-distribution");
  const activity = useApi<{ event_type: string; count: number }[]>("/dashboard/activity-distribution?days=7");
  const recent = useApi<Page<AlertSummary>>("/alerts?page_size=6&sort=created_at&order=desc");
  const s = summary.data;

  return (
    <>
      <PageHeader
        title="Overview"
        subtitle={s ? (s.model_loaded ? `AI model ${s.model_version} is active` : "AI model not loaded: rules only") : undefined}
      />

      <DataState loading={summary.loading} error={summary.error} onRetry={summary.reload}>
        {s && (
          <dl className="stat-strip">
            <div>
              <dt>Monitored users</dt>
              <dd>{s.total_users}</dd>
            </div>
            <div title={s.active_users_definition}>
              <dt>Active users</dt>
              <dd>{s.active_users}</dd>
              <small>activity in the last 7 days</small>
            </div>
            <div>
              <dt>Open alerts</dt>
              <dd>{s.open_alerts}</dd>
              <small>{s.investigating_alerts} under investigation</small>
            </div>
            <div className={s.critical_alerts > 0 ? "stat-critical" : undefined}>
              <dt>Critical alerts</dt>
              <dd>{s.critical_alerts}</dd>
              <small>open or investigating</small>
            </div>
            <div>
              <dt>High-risk users</dt>
              <dd>{s.high_risk_users}</dd>
              <small>high or critical in 7 days</small>
            </div>
            <div>
              <dt>Events, last 24 h</dt>
              <dd>{s.activities_last_24h.toLocaleString()}</dd>
            </div>
          </dl>
        )}
      </DataState>

      <div className="grid-2">
        <section className="panel">
          <h2>Alerts per day</h2>
          <p className="panel-note">Last 14 days, by the day the activity happened. Click a day to see its alerts.</p>
          <DataState loading={overTime.loading} error={overTime.error} onRetry={overTime.reload}>
            {overTime.data && (
              <>
                <ColumnChart
                  ariaLabel="Alerts per day by risk level"
                  columns={overTime.data.map((day) => ({
                    key: day.date,
                    label: day.date.slice(5),
                    parts: RISK_LEVELS.map((level) => ({ value: day[level], color: RISK_COLORS[level], label: humanize(level) })),
                  }))}
                  onColumnClick={(date) => navigate(`/alerts?date=${date}`)}
                />
                <ul className="legend">
                  {RISK_LEVELS.map((level) => (
                    <li key={level}>
                      <span className="swatch" style={{ background: RISK_COLORS[level] }} />
                      {humanize(level)}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </DataState>
        </section>

        <section className="panel">
          <h2>Users by current risk</h2>
          <p className="panel-note">Each user's highest daily risk score in the last 7 days.</p>
          <DataState loading={risk.loading} error={risk.error} onRetry={risk.reload}>
            {risk.data && (
              <HorizontalBars
                ariaLabel="Users per risk level"
                items={risk.data.map((item) => ({ label: humanize(item.level), value: item.count, color: RISK_COLORS[item.level] }))}
              />
            )}
          </DataState>

          <h2 className="panel-subtitle">Activity by type</h2>
          <p className="panel-note">Events recorded in the last 7 days.</p>
          <DataState loading={activity.loading} error={activity.error} empty={activity.data?.length === 0}
                     emptyMessage="No activity in the last 7 days.">
            {activity.data && (
              <HorizontalBars ariaLabel="Events per type"
                              items={activity.data.map((item) => ({ label: humanize(item.event_type), value: item.count }))} />
            )}
          </DataState>
        </section>
      </div>

      <section className="panel">
        <div className="panel-title-row">
          <h2>Recent alerts</h2>
          <a href="#/alerts">All alerts</a>
        </div>
        <DataState loading={recent.loading} error={recent.error} empty={recent.data?.items.length === 0}
                   emptyMessage="No alerts yet. Use the Detection Lab to test the detection pipeline.">
          <table className="table">
            <thead>
              <tr>
                <th>Risk</th>
                <th>User</th>
                <th>Activity day</th>
                <th>Rules triggered</th>
                <th>Status</th>
                <th>Raised</th>
              </tr>
            </thead>
            <tbody>
              {recent.data?.items.map((alert) => (
                <tr key={alert.id} className="row-link" onClick={() => navigate(`/alerts/${alert.id}`)}>
                  <td><RiskBadge level={alert.risk_level} score={alert.risk_score} /></td>
                  <td><a href={`#/alerts/${alert.id}`}>{alert.username}</a></td>
                  <td>{alert.window_date}</td>
                  <td>{alert.triggered_rule_ids.length}</td>
                  <td><StatusBadge status={alert.status} /></td>
                  <td>{formatDateTime(alert.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </DataState>
      </section>
    </>
  );
}
