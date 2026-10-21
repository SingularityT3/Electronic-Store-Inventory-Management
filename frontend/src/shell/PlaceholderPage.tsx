import { EmptyState } from './components';

/** Stands in for a feature screen until its sprint item lands and replaces the route. */
export default function PlaceholderPage({ title }: { title: string }) {
  return (
    <div className="page">
      <h1>{title}</h1>
      <EmptyState message="This screen is not available yet." />
    </div>
  );
}
