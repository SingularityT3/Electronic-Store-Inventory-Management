import type { ReactNode } from 'react';

/** A plain message for a list or screen with nothing to show, e.g. "No products found". */
export default function EmptyState({
  message,
  children,
}: {
  message: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <p>{message}</p>
      {children}
    </div>
  );
}
