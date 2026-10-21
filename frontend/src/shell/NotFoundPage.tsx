import { Link } from 'react-router-dom';

export default function NotFoundPage() {
  return (
    <div className="page">
      <h1>Page not found</h1>
      <p>
        There is nothing at this address. <Link to="/">Back to dashboard</Link>
      </p>
    </div>
  );
}
