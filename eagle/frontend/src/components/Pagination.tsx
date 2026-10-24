interface Props {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}

export function Pagination({ page, pageSize, total, onPageChange }: Props) {
  const lastPage = Math.max(1, Math.ceil(total / pageSize));
  const first = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const last = Math.min(total, page * pageSize);
  return (
    <nav className="pagination" aria-label="Pages">
      <span className="muted">
        {first}–{last} of {total}
      </span>
      <button className="button button-secondary" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
        Previous
      </button>
      <span>
        Page {page} of {lastPage}
      </span>
      <button className="button button-secondary" disabled={page >= lastPage} onClick={() => onPageChange(page + 1)}>
        Next
      </button>
    </nav>
  );
}
