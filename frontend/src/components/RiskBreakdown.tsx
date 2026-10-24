// Shows HOW a risk score was built: the rules part and the AI part stacked into the final score.
// This is the main explainability view of the dashboard.
import type { Analysis } from "../api/types";
import { formatScore } from "../utils/format";
import { RiskBadge } from "./Badges";

export function RiskBreakdown({ analysis }: { analysis: Analysis }) {
  const b = analysis.score_breakdown;
  const ruleShare = b.rule_weight * b.rule_score;
  const aiShare = b.ai_score === null ? 0 : b.ai_weight * b.ai_score;
  const floorShare = Math.max(0, analysis.risk_score - ruleShare - aiShare);

  return (
    <section className="breakdown" aria-label="Risk score breakdown">
      <div className="breakdown-head">
        <div>
          <div className="breakdown-score">{formatScore(analysis.risk_score)}</div>
          <div className="muted">final risk score out of 100</div>
        </div>
        <RiskBadge level={analysis.risk_level} />
      </div>

      <div className="breakdown-bar" role="img"
           aria-label={`Rules contribute ${formatScore(ruleShare)}, AI contributes ${formatScore(aiShare)}`}>
        <span className="segment segment-rules" style={{ width: `${ruleShare}%` }} />
        <span className="segment segment-ai" style={{ width: `${aiShare}%` }} />
        {floorShare > 0 && <span className="segment segment-floor" style={{ width: `${floorShare}%` }} />}
        {[25, 50, 75].map((mark) => (
          <span key={mark} className="breakdown-mark" style={{ left: `${mark}%` }} />
        ))}
      </div>

      <dl className="breakdown-legend">
        <div>
          <dt><span className="swatch swatch-rules" />Cybersecurity rules</dt>
          <dd>
            {formatScore(b.rule_score)}/100 × {b.rule_weight} = <strong>{formatScore(ruleShare)}</strong>
          </dd>
        </div>
        <div>
          <dt><span className="swatch swatch-ai" />AI anomaly model</dt>
          <dd>
            {b.ai_score === null ? (
              "unavailable (rules only)"
            ) : (
              <>
                {formatScore(b.ai_score)}/100 × {b.ai_weight} = <strong>{formatScore(aiShare)}</strong>
              </>
            )}
          </dd>
        </div>
        {b.critical_floor_applied && (
          <div>
            <dt><span className="swatch swatch-floor" />Critical-rule floor</dt>
            <dd>
              raised by <strong>{formatScore(floorShare)}</strong>
            </dd>
          </div>
        )}
      </dl>
      <p className="breakdown-formula">{b.formula}</p>
    </section>
  );
}
