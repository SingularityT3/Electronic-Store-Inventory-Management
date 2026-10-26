import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { api, ApiError } from '../../api';
import { DataTable, FormField } from '../../shell/components';
import { can, useAuth } from '../auth';

interface StockLevel {
  product_id: number;
  product_name: string;
  sku: string;
  category_id: number;
  category_name: string;
  variant_id: number | null;
  variant_sku: string | null;
  variant_attributes: Record<string, unknown> | null;
  location_id: number;
  location_name: string;
  quantity: number;
  total_quantity: number;
  reorder_threshold: number;
  reorder_to_level: number;
}

interface Location {
  id: number;
  name: string;
  type: string;
}

function itemLabel(row: StockLevel): string {
  return row.variant_sku
    ? `${row.product_name} (${row.variant_sku})`
    : `${row.product_name} (${row.sku})`;
}

const REASON_CODES = [
  ['correction', 'Correction'],
  ['damage', 'Damage'],
  ['loss', 'Loss'],
] as const;

function AdjustStockForm({
  row,
  onDone,
  onCancel,
}: {
  row: StockLevel;
  onDone: (message: string) => void;
  onCancel: () => void;
}) {
  const [change, setChange] = useState('');
  const [reasonCode, setReasonCode] = useState('correction');
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    const parsed = Number(change);
    if (!Number.isSafeInteger(parsed) || parsed === 0) {
      setError('Enter a non-zero whole-number quantity change.');
      return;
    }
    if (!reason.trim()) {
      setError('Reason is required for stock adjustment');
      return;
    }
    setSubmitting(true);
    try {
      await api('/stock/adjustments', {
        method: 'POST',
        body: {
          product_id: row.product_id,
          variant_id: row.variant_id,
          location_id: row.location_id,
          quantity_change: parsed,
          reason_code: reasonCode,
          reason: reason.trim(),
        },
      });
      onDone(`Stock adjusted for ${itemLabel(row)} at ${row.location_name}.`);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not adjust stock.');
      setSubmitting(false);
    }
  }

  return (
    <form aria-label="Adjust stock" onSubmit={submit}>
      <h2>
        Adjust stock: {itemLabel(row)} at {row.location_name} (currently {row.quantity})
      </h2>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <FormField label="Quantity change" hint="Positive adds stock, negative removes it.">
        {(field) => (
          <input
            {...field}
            type="number"
            step="1"
            value={change}
            onChange={(event) => setChange(event.target.value)}
          />
        )}
      </FormField>
      <FormField label="Reason type">
        {(field) => (
          <select
            {...field}
            value={reasonCode}
            onChange={(event) => setReasonCode(event.target.value)}
          >
            {REASON_CODES.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        )}
      </FormField>
      <FormField label="Reason">
        {(field) => (
          <textarea {...field} value={reason} onChange={(event) => setReason(event.target.value)} />
        )}
      </FormField>
      <button type="submit" disabled={submitting}>
        {submitting ? 'Adjusting…' : 'Adjust stock'}
      </button>{' '}
      <button type="button" onClick={onCancel}>
        Cancel
      </button>
    </form>
  );
}

/** Reorder threshold and reorder-to level for one item at one location (FR-2.3, SRS A-4). */
function ReorderSettingsForm({
  row,
  onDone,
  onCancel,
}: {
  row: StockLevel;
  onDone: (message: string) => void;
  onCancel: () => void;
}) {
  const [threshold, setThreshold] = useState(String(row.reorder_threshold));
  const [reorderTo, setReorderTo] = useState(
    row.reorder_to_level === 2 * row.reorder_threshold ? '' : String(row.reorder_to_level),
  );
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    const parsedThreshold = Number(threshold);
    const parsedReorderTo = reorderTo.trim() === '' ? null : Number(reorderTo);
    if (!Number.isSafeInteger(parsedThreshold) || parsedThreshold < 0) {
      setError('Enter a whole-number threshold of 0 or more.');
      return;
    }
    if (
      parsedReorderTo !== null &&
      (!Number.isSafeInteger(parsedReorderTo) || parsedReorderTo < parsedThreshold)
    ) {
      setError('Reorder-to level must be a whole number at or above the threshold.');
      return;
    }
    setSubmitting(true);
    try {
      await api('/stock/levels/reorder-settings', {
        method: 'PATCH',
        body: {
          product_id: row.product_id,
          variant_id: row.variant_id,
          location_id: row.location_id,
          reorder_threshold: parsedThreshold,
          reorder_to_level: parsedReorderTo,
        },
      });
      onDone(`Reorder settings saved for ${itemLabel(row)} at ${row.location_name}.`);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not save reorder settings.');
      setSubmitting(false);
    }
  }

  return (
    <form aria-label="Reorder settings" onSubmit={submit}>
      <h2>
        Reorder settings: {itemLabel(row)} at {row.location_name}
      </h2>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <FormField
        label="Reorder threshold"
        hint="A low-stock alert is raised when stock is at or below this level."
      >
        {(field) => (
          <input
            {...field}
            type="number"
            min="0"
            step="1"
            value={threshold}
            onChange={(event) => setThreshold(event.target.value)}
          />
        )}
      </FormField>
      <FormField
        label="Reorder-to level"
        hint="Leave blank to use twice the threshold. The reorder report suggests ordering up to it."
      >
        {(field) => (
          <input
            {...field}
            type="number"
            min="0"
            step="1"
            value={reorderTo}
            onChange={(event) => setReorderTo(event.target.value)}
          />
        )}
      </FormField>
      <button type="submit" disabled={submitting}>
        {submitting ? 'Saving…' : 'Save reorder settings'}
      </button>{' '}
      <button type="button" onClick={onCancel}>
        Cancel
      </button>
    </form>
  );
}

export default function StockLevelsPage() {
  const { user } = useAuth();
  const canAdjust = can(user, 'stock.adjust');
  const [adjusting, setAdjusting] = useState<StockLevel | null>(null);
  const [configuring, setConfiguring] = useState<StockLevel | null>(null);
  const [notice, setNotice] = useState('');
  const [levels, setLevels] = useState<StockLevel[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);
  const [locationFilter, setLocationFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [productFilter, setProductFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [reloadCount, setReloadCount] = useState(0);

  useEffect(() => {
    let current = true;
    Promise.all([api<StockLevel[]>('/stock/levels'), api<Location[]>('/stock/locations')])
      .then(([stockLevels, stockLocations]) => {
        if (!current) return;
        setLevels(stockLevels);
        setLocations(stockLocations);
        setError('');
      })
      .catch((cause: unknown) => {
        if (!current) return;
        setError(cause instanceof ApiError ? cause.message : 'Could not load stock levels.');
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, [reloadCount]);

  const categories = useMemo(
    () =>
      [...new Map(levels.map((row) => [row.category_id, row.category_name])).entries()].sort(
        (a, b) => a[1].localeCompare(b[1]),
      ),
    [levels],
  );
  const products = useMemo(
    () =>
      [
        ...new Map(
          levels.map((row) => [row.product_id, `${row.product_name} (${row.sku})`]),
        ).entries(),
      ].sort((a, b) => a[1].localeCompare(b[1])),
    [levels],
  );
  const filtered = levels.filter(
    (row) =>
      (!locationFilter || row.location_id === Number(locationFilter)) &&
      (!categoryFilter || row.category_id === Number(categoryFilter)) &&
      (!productFilter || row.product_id === Number(productFilter)),
  );

  if (loading) return <p className="loading">Loading stock levels…</p>;

  return (
    <div className="page">
      <header className="page-header">
        <h1>Stock levels</h1>
      </header>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {!error && (
        <>
          {adjusting && (
            <AdjustStockForm
              key={`${adjusting.product_id}-${adjusting.variant_id}-${adjusting.location_id}`}
              row={adjusting}
              onCancel={() => setAdjusting(null)}
              onDone={(message) => {
                setAdjusting(null);
                setNotice(message);
                setReloadCount((count) => count + 1);
              }}
            />
          )}
          {configuring && (
            <ReorderSettingsForm
              key={`${configuring.product_id}-${configuring.variant_id}-${configuring.location_id}`}
              row={configuring}
              onCancel={() => setConfiguring(null)}
              onDone={(message) => {
                setConfiguring(null);
                setNotice(message);
                setReloadCount((count) => count + 1);
              }}
            />
          )}
          <form className="audit-filters" aria-label="Filter stock levels">
            <label>
              Location
              <select
                aria-label="Location"
                value={locationFilter}
                onChange={(event) => setLocationFilter(event.target.value)}
              >
                <option value="">All locations</option>
                {locations.map((location) => (
                  <option key={location.id} value={location.id}>
                    {location.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Category
              <select
                aria-label="Category"
                value={categoryFilter}
                onChange={(event) => setCategoryFilter(event.target.value)}
              >
                <option value="">All categories</option>
                {categories.map(([id, name]) => (
                  <option key={id} value={id}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Product
              <select
                aria-label="Product"
                value={productFilter}
                onChange={(event) => setProductFilter(event.target.value)}
              >
                <option value="">All products</option>
                {products.map(([id, label]) => (
                  <option key={id} value={id}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          </form>
          <DataTable
            caption="Stock levels"
            columns={[
              { header: 'Product', cell: itemLabel },
              { header: 'Category', cell: (row) => row.category_name },
              { header: 'Location', cell: (row) => row.location_name },
              { header: 'Quantity', cell: (row) => row.quantity },
              { header: 'Combined total', cell: (row) => row.total_quantity },
              {
                header: 'Reorder threshold',
                cell: (row) =>
                  row.quantity <= row.reorder_threshold
                    ? `${row.reorder_threshold} (${row.quantity === 0 ? 'out of stock' : 'low'})`
                    : row.reorder_threshold,
              },
              ...(canAdjust
                ? [
                    {
                      header: 'Actions',
                      cell: (row: StockLevel) => (
                        <>
                          <button
                            type="button"
                            aria-label={`Adjust ${itemLabel(row)} at ${row.location_name}`}
                            onClick={() => {
                              setNotice('');
                              setConfiguring(null);
                              setAdjusting(row);
                            }}
                          >
                            Adjust
                          </button>{' '}
                          <button
                            type="button"
                            aria-label={`Reorder settings for ${itemLabel(row)} at ${row.location_name}`}
                            onClick={() => {
                              setNotice('');
                              setAdjusting(null);
                              setConfiguring(row);
                            }}
                          >
                            Reorder settings
                          </button>
                        </>
                      ),
                    },
                  ]
                : []),
            ]}
            rows={filtered}
            rowKey={(row) => `${row.product_id}-${row.variant_id ?? 'product'}-${row.location_id}`}
            emptyMessage="No stock levels match these filters."
          />
        </>
      )}
    </div>
  );
}
