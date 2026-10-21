import { Link } from 'react-router-dom';

/** Shown in place of a screen the signed-in role may not use. */
export default function AccessDenied({ what = 'this page' }: { what?: string }) {
  return (
    <div className="page access-denied">
      <h1>Access denied</h1>
      <p role="alert" className="error">
        You do not have permission to view {what}.
      </p>
      <p>
        If you need it for your work, ask an Admin. <Link to="/">Back to dashboard</Link>
      </p>
    </div>
  );
}
