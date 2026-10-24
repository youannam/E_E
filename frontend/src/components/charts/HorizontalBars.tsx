// Simple labelled bars, drawn with plain HTML so they stay sharp and readable on a projector.
export interface BarItem {
  label: string;
  value: number;
  color?: string;
}

export function HorizontalBars({ items, ariaLabel }: { items: BarItem[]; ariaLabel: string }) {
  const max = Math.max(1, ...items.map((item) => item.value));
  return (
    <ul className="hbars" aria-label={ariaLabel}>
      {items.map((item) => (
        <li key={item.label}>
          <span className="hbars-label">{item.label}</span>
          <span className="hbars-track">
            <span className="hbars-fill" style={{ width: `${(item.value / max) * 100}%`, background: item.color }} />
          </span>
          <span className="hbars-value">{item.value.toLocaleString()}</span>
        </li>
      ))}
    </ul>
  );
}
