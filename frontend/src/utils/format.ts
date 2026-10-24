// Small display helpers. Pure functions, so they are easy to unit test (format.test.ts).
import type { RiskLevel } from "../api/types";

const pad = (n: number) => String(n).padStart(2, "0");

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  // System times (alert created, login) come with a timezone ("...Z"): show them in the viewer's local time.
  if (/(Z|[+-]\d\d:\d\d)$/.test(value)) {
    const d = new Date(value);
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
  // Activity times come without a timezone (local organization time): show them as they are.
  const [day, time = ""] = value.split("T");
  return `${day} ${time.slice(0, 5)}`.trim();
}

export function formatTime(value: string): string {
  return value.split("T")[1]?.slice(0, 8) ?? value;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

export function formatScore(score: number | null | undefined): string {
  if (score === null || score === undefined) return "n/a";
  return Number.isInteger(score) ? String(score) : score.toFixed(1);
}

/** "FILE_DOWNLOAD" -> "File download" */
export function humanize(value: string): string {
  const words = value.toLowerCase().replace(/_/g, " ").replace(/\b(usb|mb|ai)\b/g, (word) => word.toUpperCase());
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export const RISK_COLORS: Record<RiskLevel, string> = {
  LOW: "var(--risk-low)",
  MEDIUM: "var(--risk-medium)",
  HIGH: "var(--risk-high)",
  CRITICAL: "var(--risk-critical)",
};

/** Build "?a=1&b=2", leaving out empty values so the API only receives real filters. */
export function buildQuery(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === "") continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export function yesterdayIso(today = new Date()): string {
  const day = new Date(today);
  day.setDate(day.getDate() - 1);
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`;
}
