// Vertical column chart in SVG. Each column can be split into coloured parts (stacked),
// e.g. alerts per day split by risk level, or one coloured column per day for risk history.
export interface ColumnPart {
  value: number;
  color: string;
  label: string;
}

export interface Column {
  key: string;
  label: string;
  parts: ColumnPart[];
}

interface Props {
  columns: Column[];
  ariaLabel: string;
  maxValue?: number; // fixed top of the scale (e.g. 100 for risk scores)
  guideLine?: { value: number; label: string };
  onColumnClick?: (key: string) => void;
  width?: number; // drawing width; use a larger value for full-width charts so text stays small
}

const HEIGHT = 200;
const LEFT = 34;
const BOTTOM = 22;
const TOP = 8;

export function ColumnChart({ columns, ariaLabel, maxValue, guideLine, onColumnClick, width = 640 }: Props) {
  const WIDTH = width;
  const totals = columns.map((column) => column.parts.reduce((sum, part) => sum + part.value, 0));
  const top = maxValue ?? Math.max(4, ...totals);
  const plotHeight = HEIGHT - BOTTOM - TOP;
  const slot = (WIDTH - LEFT) / Math.max(1, columns.length);
  const barWidth = Math.min(28, slot * 0.7);
  const y = (value: number) => TOP + plotHeight - (value / top) * plotHeight;
  const ticks = [0, top / 2, top].map((value) => Math.round(value));
  const labelEvery = Math.ceil(columns.length / 10); // avoid overlapping date labels

  return (
    <svg className="column-chart" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={ariaLabel}>
      {ticks.map((tick) => (
        <g key={tick}>
          <line x1={LEFT} x2={WIDTH} y1={y(tick)} y2={y(tick)} className="grid-line" />
          <text x={LEFT - 6} y={y(tick) + 4} textAnchor="end" className="axis-text">
            {tick}
          </text>
        </g>
      ))}
      {guideLine && (
        <g>
          <line x1={LEFT} x2={WIDTH} y1={y(guideLine.value)} y2={y(guideLine.value)} className="guide-line" />
          <text x={LEFT + 4} y={y(guideLine.value) - 4} textAnchor="start" className="axis-text">
            {guideLine.label}
          </text>
        </g>
      )}
      {columns.map((column, index) => {
        const x = LEFT + index * slot + (slot - barWidth) / 2;
        let stacked = 0;
        return (
          <g key={column.key} className={onColumnClick ? "clickable" : undefined}
             onClick={onColumnClick ? () => onColumnClick(column.key) : undefined}>
            {column.parts.map((part) => {
              if (part.value <= 0) return null;
              const bottom = stacked;
              stacked += part.value;
              return (
                <rect key={part.label} x={x} width={barWidth} y={y(stacked)} height={y(bottom) - y(stacked)}
                      fill={part.color}>
                  <title>{`${column.label}: ${part.label} ${part.value}`}</title>
                </rect>
              );
            })}
            {index % labelEvery === 0 && (
              <text x={x + barWidth / 2} y={HEIGHT - 6} textAnchor="middle" className="axis-text">
                {column.label}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
