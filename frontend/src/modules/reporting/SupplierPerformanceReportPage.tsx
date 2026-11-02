import { useCallback, useEffect, useRef, useState, type ChangeEvent } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, api, downloadFile } from '../../api';
import { EmptyState, FormField } from '../../shell/components';

interface PricePoint {
  recorded_at: string;
  unit_price: string;
}

interface ProductPriceTrend {
  product_id: number;
  product_name: string;
  sku: string;
  variant_id: number | null;
  price_points: PricePoint[];
  first_price: string;
  latest_price: string;
  variance: string | null;
  variance_percent: string | null;
}

interface SupplierPerformance {
  supplier_id: number;
  supplier_name: string;
  purchase_order_count: number;
  total_order_value: string;
  on_time_delivery_rate: string | null;
  on_time_delivery_count: number;
  eligible_delivery_count: number;
  fulfilment_accuracy: string | null;
  quantity_ordered: number;
  quantity_accepted: number;
  price_trends: ProductPriceTrend[];
}

interface SupplierPerformanceReport {
  date_from: string;
  date_to: string;
  suppliers: SupplierPerformance[];
}

interface SupplierOption {
  supplier_id: number;
  supplier_name: string;
}

const money = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 2,
});

function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function initialPeriod(): [string, string] {
  const end = new Date();
  const start = new Date(end);
  start.setDate(start.getDate() - 29);
  return [isoDate(start), isoDate(end)];
}

function percentage(value: string | null): string {
  return value === null ? '—' : `${Number(value).toFixed(2)}%`;
}

function varianceLabel(value: string | null, percent: string | null): string {
  if (value === null) return 'Insufficient price history';
  const change = Number(value);
  const amount = money.format(Math.abs(change));
  const direction = change > 0 ? '+' : change < 0 ? '−' : '';
  const percentageChange = percent === null ? '' : ` (${Number(percent).toFixed(2)}%)`;
  return `${direction}${amount}${percentageChange}`;
}

export default function SupplierPerformanceReportPage() {
  const [[dateFrom, dateTo], setDates] = useState(initialPeriod);
  const [selectedSupplierIds, setSelectedSupplierIds] = useState<string[]>([]);
  const [supplierOptions, setSupplierOptions] = useState<SupplierOption[]>([]);
  const [report, setReport] = useState<SupplierPerformanceReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const requestRef = useRef(0);
  const [exportError, setExportError] = useState('');
  const [exporting, setExporting] = useState(false);

  const generate = useCallback(async () => {
    if (!dateFrom || !dateTo || dateFrom > dateTo) {
      requestRef.current += 1;
      setLoading(false);
      setError('The start date must be on or before the end date.');
      return;
    }
    if (dateTo > isoDate(new Date())) {
      requestRef.current += 1;
      setLoading(false);
      setError('Report dates cannot be in the future.');
      return;
    }

    const requestId = ++requestRef.current;
    const params = new URLSearchParams({ date_from: dateFrom, date_to: dateTo });
    selectedSupplierIds.forEach((supplierId) => params.append('supplier_ids', supplierId));
    setLoading(true);
    setError('');
    try {
      const result = await api<SupplierPerformanceReport>(
        `/reporting/supplier-performance?${params.toString()}`,
      );
      if (requestId === requestRef.current) {
        setReport(result);
        if (selectedSupplierIds.length === 0) setSupplierOptions(result.suppliers);
      }
    } catch (cause) {
      if (requestId !== requestRef.current) return;
      setReport(null);
      setError(
        cause instanceof ApiError
          ? cause.message
          : 'Could not load the supplier performance report.',
      );
    } finally {
      if (requestId === requestRef.current) setLoading(false);
    }
  }, [dateFrom, dateTo, selectedSupplierIds]);

  useEffect(() => {
    void generate();
    return () => {
      requestRef.current += 1;
    };
  }, [generate]);

  const suppliers = report?.suppliers ?? [];

  async function exportReport(format: 'csv' | 'pdf') {
    if (!report) return;
    const params = new URLSearchParams({
      format,
      date_from: report.date_from,
      date_to: report.date_to,
    });
    selectedSupplierIds.forEach((supplierId) => params.append('supplier_ids', supplierId));
    setExporting(true);
    setExportError('');
    try {
      await downloadFile(`/reporting/supplier-performance/export?${params.toString()}`);
    } catch (cause) {
      setExportError(cause instanceof ApiError ? cause.message : 'Export failed. Try again.');
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <h1>Supplier performance report</h1>
        <Link to="/reports">Stock valuation</Link>
      </header>
      <p>Compare deliveries, purchase orders, fulfilment and recorded prices for a date period.</p>
      <div className="supplier-report-filters">
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
        <FormField label="Suppliers to compare">
          {(props) => (
            <select
              {...props}
              multiple
              size={Math.min(Math.max(suppliers.length, 2), 6)}
              value={selectedSupplierIds}
              onChange={(event: ChangeEvent<HTMLSelectElement>) =>
                setSelectedSupplierIds(
                  Array.from(event.target.selectedOptions, (option) => option.value),
                )
              }
            >
              {supplierOptions.map((supplier) => (
                <option key={supplier.supplier_id} value={supplier.supplier_id}>
                  {supplier.supplier_name}
                </option>
              ))}
            </select>
          )}
        </FormField>
        <button type="button" onClick={() => void generate()}>
          Generate report
        </button>
      </div>
      {loading && <p className="loading">Loading supplier performance report…</p>}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {!loading && !error && suppliers.length === 0 && (
        <EmptyState message="No suppliers are available for this comparison." />
      )}
      {!loading && !error && suppliers.length > 0 && (
        <div role="group" aria-label="Export">
          <button type="button" disabled={exporting} onClick={() => void exportReport('csv')}>
            Export CSV
          </button>{' '}
          <button type="button" disabled={exporting} onClick={() => void exportReport('pdf')}>
            Export PDF
          </button>
        </div>
      )}
      {exportError && (
        <p role="alert" className="error">
          {exportError}
        </p>
      )}
      {!loading && !error && suppliers.length > 0 && (
        <section aria-label="Supplier comparison" className="supplier-performance-grid">
          {suppliers.map((supplier) => (
            <article
              aria-label={supplier.supplier_name}
              className="supplier-performance-card"
              key={supplier.supplier_id}
            >
              <h2>{supplier.supplier_name}</h2>
              <dl className="supplier-performance-metrics">
                <div>
                  <dt>On-time delivery</dt>
                  <dd>
                    {percentage(supplier.on_time_delivery_rate)}
                    {supplier.eligible_delivery_count > 0 &&
                      ` (${supplier.on_time_delivery_count}/${supplier.eligible_delivery_count})`}
                  </dd>
                </div>
                <div>
                  <dt>Purchase orders</dt>
                  <dd>{supplier.purchase_order_count}</dd>
                </div>
                <div>
                  <dt>Total order value</dt>
                  <dd>{money.format(Number(supplier.total_order_value))}</dd>
                </div>
                <div>
                  <dt>Fulfilment accuracy</dt>
                  <dd>
                    {percentage(supplier.fulfilment_accuracy)}
                    {supplier.quantity_ordered > 0 &&
                      ` (${supplier.quantity_accepted}/${supplier.quantity_ordered} units accepted)`}
                  </dd>
                </div>
              </dl>
              <h3>Price trends</h3>
              {supplier.price_trends.length === 0 ? (
                <p>No price history for this period.</p>
              ) : (
                <ul className="supplier-price-trends">
                  {supplier.price_trends.map((trend) => (
                    <li key={`${trend.product_id}-${trend.variant_id ?? 'base'}`}>
                      <strong>
                        {trend.product_name} ({trend.sku})
                      </strong>
                      <span>
                        {varianceLabel(trend.variance, trend.variance_percent)} · latest{' '}
                        {money.format(Number(trend.latest_price))}
                      </span>
                      <ul>
                        {trend.price_points.map((point) => (
                          <li key={`${point.recorded_at}-${point.unit_price}`}>
                            {new Date(point.recorded_at).toLocaleDateString()}:{' '}
                            {money.format(Number(point.unit_price))}
                          </li>
                        ))}
                      </ul>
                    </li>
                  ))}
                </ul>
              )}
            </article>
          ))}
        </section>
      )}
    </div>
  );
}
