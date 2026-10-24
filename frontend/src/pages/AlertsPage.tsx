import { useState } from "react";

import type { AlertSummary, Page } from "../api/types";
import { ALERT_STATUSES, RISK_LEVELS } from "../api/types";
import { useApi } from "../api/useApi";
import { RiskBadge, StatusBadge } from "../components/Badges";
import { DataState } from "../components/DataState";
import { PageHeader } from "../components/Layout";
import { Pagination } from "../components/Pagination";
import { buildQuery, formatDateTime, formatScore, humanize } from "../utils/format";
import { hashParams, navigate } from "../utils/router";

const PAGE_SIZE = 15;

export function AlertsPage() {
  const initial = hashParams(); // e.g. arriving from a click on the dashboard chart
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState(initial.get("status") ?? "");
  const [riskLevel, setRiskLevel] = useState(initial.get("risk_level") ?? "");
  const [userId, setUserId] = useState(initial.get("user_id") ?? "");
  const [dateFrom, setDateFrom] = useState(initial.get("date") ?? "");
  const [dateTo, setDateTo] = useState(initial.get("date") ?? "");
  const [sort, setSort] = useState("created_at:desc");
  const [page, setPage] = useState(1);

  const [sortField, order] = sort.split(":");
  const query = buildQuery({
    search: search.trim(), status, risk_level: riskLevel, user_id: userId, date_from: dateFrom, date_to: dateTo,
    sort: sortField, order, page, page_size: PAGE_SIZE,
  });
  const alerts = useApi<Page<AlertSummary>>(`/alerts${query}`);

  // Any filter change goes back to page 1.
  function update(setter: (value: string) => void) {
    return (value: string) => {
      setter(value);
      setPage(1);
    };
  }

  function clearFilters() {
    setSearch("");
    setStatus("");
    setRiskLevel("");
    setUserId("");
    setDateFrom("");
    setDateTo("");
    setPage(1);
  }

  return (
    <>
      <PageHeader title="Alerts" subtitle="Every alert was raised by the detection pipeline; open one to investigate." />

      <form className="filters" onSubmit={(e) => e.preventDefault()} aria-label="Alert filters">
        <label>
          Search
          <input type="search" placeholder="User or department" value={search}
                 onChange={(e) => update(setSearch)(e.target.value)} />
        </label>
        <label>
          Status
          <select value={status} onChange={(e) => update(setStatus)(e.target.value)}>
            <option value="">Any status</option>
            {ALERT_STATUSES.map((value) => <option key={value} value={value}>{humanize(value)}</option>)}
          </select>
        </label>
        <label>
          Risk level
          <select value={riskLevel} onChange={(e) => update(setRiskLevel)(e.target.value)}>
            <option value="">Any level</option>
            {RISK_LEVELS.map((value) => <option key={value} value={value}>{humanize(value)}</option>)}
          </select>
        </label>
        <label>
          From
          <input type="date" value={dateFrom} onChange={(e) => update(setDateFrom)(e.target.value)} />
        </label>
        <label>
          To
          <input type="date" value={dateTo} onChange={(e) => update(setDateTo)(e.target.value)} />
        </label>
        <label>
          Sort by
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="created_at:desc">Newest first</option>
            <option value="risk_score:desc">Highest risk first</option>
            <option value="window_date:desc">Latest activity day</option>
            <option value="created_at:asc">Oldest first</option>
          </select>
        </label>
        <button type="button" className="button button-secondary" onClick={clearFilters}>
          Clear filters
        </button>
      </form>

      <section className="panel">
        <DataState loading={alerts.loading && !alerts.data} error={alerts.error} onRetry={alerts.reload}
                   empty={alerts.data?.total === 0} emptyMessage="No alerts match these filters.">
          <table className="table">
            <thead>
              <tr>
                <th>Risk</th>
                <th>User</th>
                <th>Activity day</th>
                <th>Rules</th>
                <th>AI score</th>
                <th>Status</th>
                <th>Assigned to</th>
                <th>Raised</th>
              </tr>
            </thead>
            <tbody>
              {alerts.data?.items.map((alert) => (
                <tr key={alert.id} className="row-link" onClick={() => navigate(`/alerts/${alert.id}`)}>
                  <td><RiskBadge level={alert.risk_level} score={alert.risk_score} /></td>
                  <td>
                    <a href={`#/alerts/${alert.id}`}>{alert.username}</a>
                    <div className="muted small">{alert.department}</div>
                  </td>
                  <td>{alert.window_date}</td>
                  <td className="rule-list">{alert.triggered_rule_ids.map((id) => humanize(id)).join(", ") || "None (AI only)"}</td>
                  <td>{alert.ai_status === "OK" ? formatScore(alert.ai_score) : "unavailable"}</td>
                  <td><StatusBadge status={alert.status} /></td>
                  <td>{alert.assigned_to ?? <span className="muted">—</span>}</td>
                  <td>{formatDateTime(alert.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {alerts.data && <Pagination page={page} pageSize={PAGE_SIZE} total={alerts.data.total} onPageChange={setPage} />}
        </DataState>
      </section>
    </>
  );
}
