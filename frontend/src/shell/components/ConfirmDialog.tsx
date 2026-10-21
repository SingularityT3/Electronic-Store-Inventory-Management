import { useEffect, useId, useRef, type KeyboardEvent } from 'react';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Asks the user to confirm an action that cannot easily be undone, such as deleting a product.
 * Focus starts on Cancel, Tab stays inside the dialog and Escape cancels.
 */
export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const titleId = useId();
  const messageId = useId();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const before = document.activeElement as HTMLElement | null;
    cancelRef.current?.focus();
    return () => before?.focus?.();
  }, [open]);

  if (!open) return null;

  function onKeyDown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      event.stopPropagation();
      onCancel();
    } else if (event.key === 'Tab') {
      const first = cancelRef.current;
      const last = confirmRef.current;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    }
  }

  return (
    <div className="dialog-backdrop">
      <div
        className="dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={messageId}
        onKeyDown={onKeyDown}
      >
        <h2 id={titleId}>{title}</h2>
        <p id={messageId}>{message}</p>
        <div className="dialog-actions">
          <button type="button" ref={cancelRef} onClick={onCancel}>
            {cancelLabel}
          </button>
          <button type="button" ref={confirmRef} className="danger" onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
