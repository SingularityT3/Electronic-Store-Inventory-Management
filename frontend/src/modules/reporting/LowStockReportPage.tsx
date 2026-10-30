import { useEffect, useMemo, useState, type ChangeEvent } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, api } from '../../api';
import { DataTable, FormField, type Column } from '../../shell/components';

interface Location {
  id: number;
  name: string;
}

interface ReorderItem {
  product_id: number;
  product_name: string;
  sku: string;
  variant_id: number | null;
  variant_sku: string | null;
  variant_attributes: Record<string, unknown> | null;
  location_id: number;
  location_name: string;
  quantity: number;
  reorder_threshold: number;
  reorder_to_level: number;
  suggested_quantity: number;
}

function variantLabel(item: ReorderItem): string {
  const attributes = item.variant_attributes
    ? Object.entries(item.variant_attributes)
        .map(([name, value]) => `${name}: ${String(value)}`)
        .join(', ')
    : '';
  return [item.variant_sku, attributes].filter(Boolean).join(' — ') || '—';
}

function purchaseOrderHref(item: ReorderItem): string {
  const params = new URLSearchParams({
    product_id: String(item.product_id),
    location_id: String(item.location_id),
    quantity: String(item.suggested_quantity),
    product_name: item.product_name,
    sku: item.sku,
  });
  if (item.variant_id !== null) params.set('variant_id', String(item.variant_id));
  if (item.variant_sku) params.set('variant_sku', item.variant_sku);
  return `/purchase-orders?${params.toString()}`;
}

export default function LowStockReportPage() {
  const [locations, setLocations] = useState<Location[]>([]);
  const [items, setItems] = useState<ReorderItem[]>([]);
  const [locationId, setLocationId] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    const filter = locationId ? `?location_id=${encodeURIComponent(locationId)}` : '';

    Promise.all([
      api<Location[]>('/stock/locations'),
      api<ReorderItem[]>(`/reporting/reorder${filter}`),
    ])
      .then(([locationRows, reportRows]) => {
        if (!active) return;
        setLocations(locationRows);
        setItems(reportRows);
      })
      .catch((cause: unknown) => {
        if (!active) return;
        setItems([]);
        setError(
          cause instanceof ApiError ? cause.message : 'Could not load the low-stock report.',
        );
      })
      .finally(() => active && setLoading(false));

    return () => {
      active = false;
    };
  }, [locationId]);

  const columns = useMemo<Column<ReorderItem>[]>(
    () => [
      { header: 'Product / SKU', cell: (item) => `${item.product_name} (${item.sku})` },
      { header: 'Variant', cell: variantLabel },
      { header: 'Location', cell: (item) => item.location_name },
      { header: 'Current stock', cell: (item) => item.quantity },
      { header: 'Reorder threshold', cell: (item) => item.reorder_threshold },
      { header: 'Suggested quantity', cell: (item) => item.suggested_quantity },
      {
        header: 'Action',
        cell: (item) =>
          item.suggested_quantity > 0 ? (
            <Link to={purchaseOrderHref(item)} aria-label={`Create PO for ${item.sku}`}>
              Create PO
            </Link>
          ) : (
            'No reorder needed'
          ),
      },
    ],
    [],
  );

  if (loading) return <p className="loading">Loading low-stock report…</p>;

  return (
    <div className="page">
      <header className="page-header">
        <h1>Low-stock &amp; reorder report</h1>
        <Link to="/reports">Stock valuation</Link>
      </header>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {!error && (
        <>
          <FormField label="Location">
            {(props) => (
              <select
                {...props}
                value={locationId}
                onChange={(event: ChangeEvent<HTMLSelectElement>) =>
                  setLocationId(event.target.value)
                }
              >
                <option value="">All locations</option>
                {locations.map((location) => (
                  <option key={location.id} value={location.id}>
                    {location.name}
                  </option>
                ))}
              </select>
            )}
          </FormField>
          <DataTable
            caption="Low-stock and reorder report"
            columns={columns}
            rows={items}
            rowKey={(item) => `${item.product_id}-${item.variant_id ?? 'base'}-${item.location_id}`}
            emptyMessage="No products are at or below their reorder threshold."
          />
        </>
      )}
    </div>
  );
}
