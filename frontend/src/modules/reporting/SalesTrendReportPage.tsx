import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, api, downloadFile } from '../../api';
import { DataTable, EmptyState, FormField, type Column } from '../../shell/components';

interface Location {
  id: number;
  name: string;
}

interface TrendRow {
  rank: number;
  product_id: number;
  sku: string;
  name: string;
  units_sold: number;
  units_returned: number;
  net_units: number;
  net_amount: string;
  current_stock: number;
  inactive: boolean;
}

interface TrendReport {
  date_from: string;
  date_to: string;
  location_id: number | null;
  totals: {
    units_sold: number;
    units_returned: number;
    net_units: number;
    net_amount: string;
    products_with_zero_sales: number;
  };
  best: TrendRow[];
  worst: TrendRow[];
}

type Preset = 'today' | '7' | '30' | 'month' | 'custom';

const money = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 2,
});

function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function datesFor(preset: Exclude<Preset, 'custom'>): [string, string] {
  const today = new Date();
  const end = isoDate(today);
  if (preset === 'today') return [end, end];
  if (preset === 'month') return [isoDate(new Date(today.getFullYear(), today.getMonth(), 1)), end];
  const days = preset === '7' ? 6 : 29;
  const start = new Date(today);
  start.setDate(today.getDate() - days);
  return [isoDate(start), end];
}

function productLink(row: TrendRow): string {
  return `/products/search?q=${encodeURIComponent(row.sku)}`;
}

export default function SalesTrendReportPage() {
  const [preset, setPreset] = useState<Preset>('30');
  const [[dateFrom, dateTo], setDates] = useState(() => datesFor('30'));
  const [locationId, setLocationId] = useState('');
  const [locations, setLocations] = useState<Location[]>([]);
  const [report, setReport] = useState<TrendReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [exportError, setExportError] = useState('');
  const [exporting, setExporting] = useState(false);
  const requestRef = useRef(0);

  const generate = useCallback(
    async (from = dateFrom, to = dateTo) => {
      if (!from || !to || from > to) {
        setError('The start date must be on or before the end date.');
        return;
      }
      if (to > isoDate(new Date())) {
        setError('Report dates cannot be in the future.');
        return;
      }
      setLoading(true);
      setError('');
      const requestId = ++requestRef.current;
      const location = locationId ? `&location_id=${encodeURIComponent(locationId)}` : '';
      try {
        const result = await api<TrendReport>(
          `/reporting/sales-trend?date_from=${from}&date_to=${to}${location}`,
        );
        if (requestId !== requestRef.current) return;
        setReport(result);
      } catch (cause) {
        if (requestId !== requestRef.current) return;
        setReport(null);
        setError(
          cause instanceof ApiError ? cause.message : 'Could not load the sales trend report.',
        );
      } finally {
        if (requestId === requestRef.current) setLoading(false);
      }
    },
    [dateFrom, dateTo, locationId],
  );

  useEffect(() => {
    let active = true;
    api<Location[]>('/stock/locations')
      .then((rows) => active && setLocations(rows))
      .catch(() => active && setLocations([]));
    generate();
    return () => {
      active = false;
    };
  }, [generate]);

  const columns = useMemo<Column<TrendRow>[]>(
    () => [
      { header: 'Rank', cell: (row) => row.rank },
      {
        header: 'Product',
        cell: (row) => (
          <Link to={productLink(row)}>
            {row.name} ({row.sku}){row.inactive ? ' (inactive)' : ''}
          </Link>
        ),
      },
      { header: 'Units sold', cell: (row) => row.units_sold },
      { header: 'Returned', cell: (row) => row.units_returned },
      { header: 'Net units', cell: (row) => row.net_units },
      { header: 'Net amount', cell: (row) => money.format(Number(row.net_amount)) },
      { header: 'Current stock', cell: (row) => row.current_stock },
    ],
    [],
  );

  function choosePreset(value: Preset) {
    setPreset(value);
    if (value !== 'custom') setDates(datesFor(value));
  }

  async function exportReport(format: 'csv' | 'pdf') {
    setExporting(true);
    setExportError('');
    const location = locationId ? `&location_id=${encodeURIComponent(locationId)}` : '';
    try {
      await downloadFile(
        `/reporting/sales-trend/export?format=${format}&date_from=${dateFrom}&date_to=${dateTo}${location}`,
      );
    } catch (cause) {
      setExportError(cause instanceof ApiError ? cause.message : 'Export failed. Try again.');
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <h1>Sales trend report</h1>
        <Link to="/reports">Stock valuation</Link>
      </header>
      <FormField label="Period">
        {(props) => (
          <select
            {...props}
            value={preset}
            onChange={(event) => choosePreset(event.target.value as Preset)}
          >
            <option value="today">Today</option>
            <option value="7">Last 7 days</option>
            <option value="30">Last 30 days</option>
            <option value="month">This month</option>
            <option value="custom">Custom</option>
          </select>
        )}
      </FormField>
      {preset === 'custom' && (
        <div className="form-grid">
          <FormField label="From">
            {(props) => (
              <input
                {...props}
                type="date"
                value={dateFrom}
                onChange={(event: ChangeEvent<HTMLInputElement>) =>
                  setDates(([, to]) => [event.target.value, to])
                }
              />
            )}
          </FormField>
          <FormField label="To">
            {(props) => (
              <input
                {...props}
                type="date"
                value={dateTo}
                onChange={(event: ChangeEvent<HTMLInputElement>) =>
                  setDates(([from]) => [from, event.target.value])
                }
              />
            )}
          </FormField>
        </div>
      )}
      <FormField label="Location">
        {(props) => (
          <select
            {...props}
            value={locationId}
            onChange={(event) => setLocationId(event.target.value)}
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
      <button type="button" onClick={() => generate()}>
        Generate
      </button>
      {loading && <p className="loading">Loading sales trend report…</p>}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {!loading && report && (
        <>
          <p>
            Net units: <strong>{report.totals.net_units}</strong> · Gross units:{' '}
            <strong>{report.totals.units_sold}</strong> · Returned:{' '}
            <strong>{report.totals.units_returned}</strong> · Net sales:{' '}
            <strong>{money.format(Number(report.totals.net_amount))}</strong> · Zero-sales:{' '}
            <strong>{report.totals.products_with_zero_sales}</strong>
          </p>
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
          {report.best.length === 0 ? (
            <EmptyState message="No sales in this period" />
          ) : (
            <>
              <h2>Best sellers</h2>
              <DataTable
                caption="Best sellers"
                columns={columns}
                rows={report.best}
                rowKey={(row) => row.product_id}
                emptyMessage="No sales in this period"
              />
              <h2>Worst sellers</h2>
              <DataTable
                caption="Worst sellers"
                columns={columns}
                rows={report.worst}
                rowKey={(row) => row.product_id}
                emptyMessage="No products in this period"
              />
            </>
          )}
        </>
      )}
    </div>
  );
}
