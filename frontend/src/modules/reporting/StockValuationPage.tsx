import { useEffect, useMemo, useState, type ChangeEvent } from 'react';
import { ApiError, api, downloadFile } from '../../api';
import { DataTable, FormField, type Column } from '../../shell/components';

interface Location {
  id: number;
  name: string;
}

interface ValuationItem {
  product_id: number;
  product_name: string;
  sku: string;
  variant_id: number | null;
  variant_sku: string | null;
  variant_attributes: Record<string, unknown> | null;
  location_id: number;
  location_name: string;
  quantity: number;
  unit_cost: string;
  value: string;
  cost_not_set: boolean;
}

interface ValuationReport {
  items: ValuationItem[];
  total_value: string;
}

const money = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const unitMoney = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 4,
  maximumFractionDigits: 4,
});

function variantLabel(item: ValuationItem): string {
  const attributes = item.variant_attributes
    ? Object.entries(item.variant_attributes)
        .map(([name, value]) => `${name}: ${String(value)}`)
        .join(', ')
    : '';
  return [item.variant_sku, attributes].filter(Boolean).join(' — ') || '—';
}

export default function StockValuationPage() {
  const [locations, setLocations] = useState<Location[]>([]);
  const [report, setReport] = useState<ValuationReport | null>(null);
  const [locationId, setLocationId] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [exportError, setExportError] = useState('');
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    const filter = locationId ? `?location_id=${encodeURIComponent(locationId)}` : '';

    Promise.all([
      api<Location[]>('/stock/locations'),
      api<ValuationReport>(`/reporting/valuation${filter}`),
    ])
      .then(([locationRows, valuation]) => {
        if (!active) return;
        setLocations(locationRows);
        setReport(valuation);
      })
      .catch((cause: unknown) => {
        if (!active) return;
        setReport(null);
        setError(
          cause instanceof ApiError ? cause.message : 'Could not load the stock valuation report.',
        );
      })
      .finally(() => active && setLoading(false));

    return () => {
      active = false;
    };
  }, [locationId]);

  const columns = useMemo<Column<ValuationItem>[]>(
    () => [
      { header: 'Product / SKU', cell: (item) => `${item.product_name} (${item.sku})` },
      { header: 'Variant', cell: variantLabel },
      { header: 'Location', cell: (item) => item.location_name },
      { header: 'Quantity', cell: (item) => item.quantity },
      {
        header: 'Unit cost',
        cell: (item) =>
          item.cost_not_set ? <span>Cost not set</span> : unitMoney.format(Number(item.unit_cost)),
      },
      { header: 'Inventory value', cell: (item) => money.format(Number(item.value)) },
    ],
    [],
  );

  async function exportReport(format: 'csv' | 'pdf') {
    setExporting(true);
    setExportError('');
    const filter = locationId ? `&location_id=${encodeURIComponent(locationId)}` : '';
    try {
      await downloadFile(`/reporting/valuation/export?format=${format}${filter}`);
    } catch (cause) {
      setExportError(
        cause instanceof ApiError
          ? `Export failed: ${cause.message} Try again.`
          : 'Export failed. Try again.',
      );
    } finally {
      setExporting(false);
    }
  }

  if (loading) return <p className="loading">Loading stock valuation…</p>;

  return (
    <div className="page">
      <header className="page-header">
        <h1>Stock valuation</h1>
      </header>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {!error && report && (
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
          <div role="group" aria-label="Export">
            <button type="button" disabled={exporting} onClick={() => exportReport('csv')}>
              Export CSV
            </button>{' '}
            <button type="button" disabled={exporting} onClick={() => exportReport('pdf')}>
              Export PDF
            </button>
          </div>
          {exportError && (
            <p role="alert" className="error">
              {exportError}
            </p>
          )}
          <p>
            Total inventory value: <strong>{money.format(Number(report.total_value))}</strong>
          </p>
          <DataTable
            caption="Stock valuation"
            columns={columns}
            rows={report.items}
            rowKey={(item) => `${item.product_id}-${item.variant_id ?? 'base'}-${item.location_id}`}
            emptyMessage="No stock valuation data for this location."
          />
        </>
      )}
    </div>
  );
}
