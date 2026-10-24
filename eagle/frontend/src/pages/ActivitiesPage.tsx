import { useState } from "react";

import type { Activity, Page, UserSummary } from "../api/types";
import { EVENT_TYPES, SENSITIVITY_LEVELS } from "../api/types";
import { useApi } from "../api/useApi";
import { SensitivityText, SimulatedTag } from "../components/Badges";
import { DataState } from "../components/DataState";
import { PageHeader } from "../components/Layout";
import { Pagination } from "../components/Pagination";
import { buildQuery, formatBytes, formatDateTime, humanize } from "../utils/format";
import { hashParams } from "../utils/router";

const PAGE_SIZE = 25;

export function ActivitiesPage() {
  const [userId, setUserId] = useState(hashParams().get("user_id") ?? "");
  const [eventType, setEventType] = useState("");
  const [sensitivity, setSensitivity] = useState("");
  const [source, setSource] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  const users = useApi<Page<UserSummary>>("/users?page_size=100&sort=username");
  const query = buildQuery({
    user_id: userId, event_type: eventType, sensitivity, source, search: search.trim(),
    // Dates are inclusive for the analyst: "To" means until the end of that day.
    start: start ? `${start}T00:00:00` : "", end: end ? `${end}T23:59:59` : "", page, page_size: PAGE_SIZE,
  });
  const activities = useApi<Page<Activity>>(`/activities${query}`);

  function change(setter: (value: string) => void) {
    return (event: { target: { value: string } }) => {
      setter(event.target.value);
      setPage(1);
    };
  }

  return (
    <>
      <PageHeader title="Activity log" subtitle="Every event received by the ingestion API, newest first." />
      <form className="filters" onSubmit={(e) => e.preventDefault()} aria-label="Activity filters">
        <label>
          User
          <select value={userId} onChange={change(setUserId)}>
            <option value="">All users</option>
            {users.data?.items.map((user) => <option key={user.id} value={user.id}>{user.username}</option>)}
          </select>
        </label>
        <label>
          Event type
          <select value={eventType} onChange={change(setEventType)}>
            <option value="">All types</option>
            {EVENT_TYPES.map((type) => <option key={type} value={type}>{humanize(type)}</option>)}
          </select>
        </label>
        <label>
          Sensitivity
          <select value={sensitivity} onChange={change(setSensitivity)}>
            <option value="">Any</option>
            {SENSITIVITY_LEVELS.map((level) => <option key={level} value={level}>{humanize(level)}</option>)}
          </select>
        </label>
        <label>
          Source
          <select value={source} onChange={change(setSource)}>
            <option value="">Any source</option>
            <option value="SIMULATOR">Simulator</option>
            <option value="API">API</option>
            <option value="IMPORT">Import</option>
          </select>
        </label>
        <label>
          From
          <input type="date" value={start} onChange={change(setStart)} />
        </label>
        <label>
          To
          <input type="date" value={end} onChange={change(setEnd)} />
        </label>
        <label>
          Resource or user
          <input type="search" placeholder="e.g. payroll" value={search} onChange={change(setSearch)} />
        </label>
      </form>

      <section className="panel">
        <DataState loading={activities.loading && !activities.data} error={activities.error} onRetry={activities.reload}
                   empty={activities.data?.total === 0} emptyMessage="No activity matches these filters.">
          <table className="table">
            <thead>
              <tr>
                <th>Time</th>
                <th>User</th>
                <th>Event</th>
                <th>Resource</th>
                <th>Sensitivity</th>
                <th>Size</th>
                <th>Device</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {activities.data?.items.map((activity) => (
                <tr key={activity.id}>
                  <td className="nowrap">{formatDateTime(activity.timestamp)}</td>
                  <td><a href={`#/users/${activity.user_id}`}>{activity.username}</a></td>
                  <td>{humanize(activity.event_type)}</td>
                  <td className="truncate" title={activity.resource ?? ""}>{activity.resource ?? <span className="muted">—</span>}</td>
                  <td><SensitivityText value={activity.sensitivity} /></td>
                  <td>{activity.file_size_bytes ? formatBytes(activity.file_size_bytes) : <span className="muted">—</span>}</td>
                  <td>{activity.device_id ?? <span className="muted">—</span>}</td>
                  <td>{activity.is_simulated ? <SimulatedTag /> : humanize(activity.source)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {activities.data && (
            <Pagination page={page} pageSize={PAGE_SIZE} total={activities.data.total} onPageChange={setPage} />
          )}
        </DataState>
      </section>
    </>
  );
}
