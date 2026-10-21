import { usePopover } from './usePopover';

/**
 * Placeholder for the notification bell. Low-stock alerts (#28) and order status updates (#29)
 * will fill the panel; until then it always reports that there is nothing new.
 */
export default function NotificationBell() {
  const { open, setOpen, ref } = usePopover<HTMLDivElement>();
  return (
    <div className="popover" ref={ref}>
      <button
        type="button"
        className="header-button"
        aria-label="Notifications"
        aria-expanded={open}
        aria-controls="notifications-panel"
        onClick={() => setOpen(!open)}
      >
        <span aria-hidden="true">🔔</span>
      </button>
      {open && (
        <div
          id="notifications-panel"
          className="popover-panel"
          role="region"
          aria-label="Notifications"
        >
          <p>No new notifications.</p>
        </div>
      )}
    </div>
  );
}
