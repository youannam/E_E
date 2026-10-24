// Asks "are you sure?" before important changes (alert status, rule settings).
import { useEffect, useRef } from "react";

interface Props {
  title: string;
  message: string;
  confirmLabel: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({ title, message, confirmLabel, busy, onConfirm, onCancel }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog && !dialog.open) dialog.showModal(); // showModal traps focus and handles Escape
  }, []);

  return (
    <dialog ref={dialogRef} className="dialog" onCancel={onCancel} aria-labelledby="dialog-title">
      <h2 id="dialog-title">{title}</h2>
      <p>{message}</p>
      <div className="dialog-actions">
        <button className="button button-secondary" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
        <button className="button" onClick={onConfirm} disabled={busy} autoFocus>
          {busy ? "Saving…" : confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
