// TypeScript mirror of the API contract in backend/schemas.py.
// Field names must match the backend exactly; see docs/API_SPECIFICATION.md.

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type AlertStatus = "OPEN" | "INVESTIGATING" | "RESOLVED" | "FALSE_POSITIVE";
export type Role = "ADMIN" | "ANALYST" | (string & {});

export const RISK_LEVELS: RiskLevel[] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];
export const ALERT_STATUSES: AlertStatus[] = ["OPEN", "INVESTIGATING", "RESOLVED", "FALSE_POSITIVE"];
export const EVENT_TYPES = [
  "LOGIN", "LOGOUT", "FILE_ACCESS", "FILE_DOWNLOAD", "FILE_UPLOAD", "FILE_DELETE",
  "USB_CONNECT", "USB_TRANSFER", "EMAIL_SENT", "APPLICATION_USAGE",
];
export const SENSITIVITY_LEVELS = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"];

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface Account {
  id: number;
  username: string;
  email: string | null;
  role: Role;
  job_role?: string;
  permissions?: string[];
  is_active: boolean;
  last_login: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  account: Account;
}

export interface Activity {
  id: number;
  user_id: number;
  username: string;
  timestamp: string;
  event_type: string;
  resource: string | null;
  sensitivity: string | null;
  file_size_bytes: number | null;
  device_id: string | null;
  source: string;
  is_simulated: boolean;
  details: Record<string, unknown>;
}

export interface TriggeredRule {
  rule_id: string;
  name: string;
  severity: string;
  contribution: number;
  reason: string;
  evidence: Record<string, unknown>;
}

export interface ScoreBreakdown {
  rule_score: number;
  ai_score: number | null;
  rule_weight: number;
  ai_weight: number;
  weighted_score: number;
  critical_floor_applied: boolean;
  formula: string;
}

export interface Analysis {
  id: number;
  user_id: number;
  username: string;
  window_date: string;
  event_count: number;
  features: Record<string, number>;
  baseline_type: string;
  rule_score: number;
  triggered_rules: TriggeredRule[];
  ai_status: "OK" | "UNAVAILABLE";
  ai_is_anomaly: boolean | null;
  ai_score: number | null;
  ai_raw_score: number | null;
  model_version: string | null;
  risk_score: number;
  risk_level: RiskLevel;
  score_breakdown: ScoreBreakdown;
  alert_id: number | null;
  analyzed_at: string;
}

export interface UserSummary {
  id: number;
  username: string;
  email: string | null;
  department: string;
  job_role: string;
  status: string;
  is_synthetic: boolean;
  current_risk_score: number;
  current_risk_level: RiskLevel;
  alert_count: number;
  open_alert_count: number;
  last_activity_at: string | null;
  last_login: string | null;
}

export interface Baseline {
  baseline_type: string;
  observation_days: number;
  window_start: string | null;
  window_end: string | null;
  feature_means: Record<string, number>;
  feature_stds: Record<string, number>;
  generated_at: string;
}

export interface UserDetail extends UserSummary {
  profile: Baseline | null;
  statistics: {
    period_days: number;
    event_counts: Record<string, number>;
    active_days: number;
    average_events_per_active_day: number;
    devices: string[];
  };
}

export interface RiskHistoryPoint {
  window_date: string;
  risk_score: number;
  risk_level: RiskLevel;
  rule_score: number;
  ai_score: number | null;
  ai_is_anomaly: boolean | null;
  event_count: number;
  alert_id: number | null;
}

export interface AlertSummary {
  id: number;
  user_id: number;
  username: string;
  department: string;
  window_date: string;
  created_at: string;
  updated_at: string;
  risk_score: number;
  risk_level: RiskLevel;
  rule_score: number;
  ai_status: string;
  ai_score: number | null;
  ai_is_anomaly: boolean | null;
  model_version: string | null;
  status: AlertStatus;
  triggered_rule_ids: string[];
  occurrence_count: number;
  assigned_to: string | null;
}

export interface AlertHistoryEntry {
  id: number;
  action: string;
  old_status: string | null;
  new_status: string | null;
  note: string | null;
  actor: string | null;
  created_at: string;
}

export interface AlertDetail extends AlertSummary {
  triggered_rules: TriggeredRule[];
  explanation: string;
  resolved_at: string | null;
  resolution_notes: string | null;
  user: UserSummary;
  activities: Activity[];
  history: AlertHistoryEntry[];
  analysis: Analysis | null;
}

export interface DashboardSummary {
  total_users: number;
  active_users: number;
  active_users_definition: string;
  open_alerts: number;
  investigating_alerts: number;
  critical_alerts: number;
  high_risk_users: number;
  activities_last_24h: number;
  model_loaded: boolean;
  model_version: string | null;
}

export interface AlertsOverTimeItem {
  date: string;
  LOW: number;
  MEDIUM: number;
  HIGH: number;
  CRITICAL: number;
  total: number;
}

export interface Scenario {
  id: string;
  name: string;
  description: string;
  expected_signals: string[];
  suspicious: boolean;
}

export interface SimulationResponse {
  scenario_id: string;
  scenario_name: string;
  date: string;
  seed: number;
  intensity: number;
  events_created: number;
  activities: Activity[];
  analysis: Analysis | null;
  alert: AlertSummary | null;
}

export interface Rule {
  rule_id: string;
  name: string;
  description: string;
  severity: string;
  required_fields: string[];
  time_window: string;
  enabled: boolean;
  weight: number;
  parameters: Record<string, unknown>;
}

export interface ModelStatus {
  loaded: boolean;
  message: string;
  version: string | null;
  trained_at: string | null;
  feature_names: string[];
  metrics: Record<string, unknown>;
}
