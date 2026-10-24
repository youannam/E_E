// One component for the three "not ready yet" states every data view needs.
import type { ReactNode } from "react";

interface Props {
  loading: boolean;
  error: string | null;
  empty?: boolean;
  emptyMessage?: ReactNode;
  onRetry?: () => void;
  children: ReactNode;
}

export function DataState({ loading, error, empty, emptyMessage, onRetry, children }: Props) {
  if (error) {
    return (
      <div className="state state-error" role="alert">
        <p>{error}</p>
        {onRetry && (
          <button className="button button-secondary" onClick={onRetry}>
            Try again
          </button>
        )}
      </div>
    );
  }
  if (loading) {
    return (
      <div className="state" aria-busy="true">
        Loading…
      </div>
    );
  }
  if (empty) {
    return <div className="state state-empty">{emptyMessage ?? "Nothing to show yet."}</div>;
  }
  return <>{children}</>;
}
