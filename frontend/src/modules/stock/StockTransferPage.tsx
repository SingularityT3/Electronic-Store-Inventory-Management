import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { api, ApiError } from '../../api';
import { FormField } from '../../shell/components';
import { useAuth } from '../auth';

interface StockLevel {
  product_id: number;
  product_name: string;
  sku: string;
  variant_id: number | null;
  variant_sku: string | null;
  variant_attributes: Record<string, unknown> | null;
  location_id: number;
  location_name: string;
  quantity: number;
}

interface Location {
  id: number;
  name: string;
  type: string;
}

interface TransferItem {
  key: string;
  product_id: number;
  variant_id: number | null;
  product_name: string;
  sku: string;
}

function itemKey(productId: number, variantId: number | null): string {
  return `${productId}:${variantId ?? ''}`;
}

function itemLabel(item: TransferItem): string {
  return `${item.product_name} (${item.sku})`;
}

export default function StockTransferPage() {
  const { user } = useAuth();
  const canChooseAnySource = user?.role === 'admin' || user?.role === 'manager';
  const [levels, setLevels] = useState<StockLevel[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);
  const [sourceLocationId, setSourceLocationId] = useState(
    canChooseAnySource || user?.location_id == null ? '' : String(user.location_id),
  );
  const [destinationLocationId, setDestinationLocationId] = useState('');
  const [itemSelection, setItemSelection] = useState('');
  const [quantity, setQuantity] = useState('');
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [success, setSuccess] = useState('');

  useEffect(() => {
    let current = true;
    Promise.all([api<StockLevel[]>('/stock/levels'), api<Location[]>('/stock/transfers/locations')])
      .then(([stockLevels, transferLocations]) => {
        if (!current) return;
        setLevels(stockLevels);
        setLocations(transferLocations);
        setLoadError('');
      })
      .catch((cause: unknown) => {
        if (!current) return;
        setLoadError(
          cause instanceof ApiError ? cause.message : 'Could not load stock transfer options.',
        );
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, []);

  useEffect(() => {
    if (!canChooseAnySource && user?.location_id != null) {
      setSourceLocationId(String(user.location_id));
    }
  }, [canChooseAnySource, user?.location_id]);

  const sourceLocations = useMemo(
    () =>
      canChooseAnySource
        ? locations
        : locations.filter((location) => location.id === user?.location_id),
    [canChooseAnySource, locations, user?.location_id],
  );

  const items = useMemo(() => {
    const itemRows = new Map<string, TransferItem>();
    for (const row of levels) {
      if (row.quantity <= 0 || (sourceLocationId && row.location_id !== Number(sourceLocationId))) {
        continue;
      }
      const variantId = row.variant_id;
      const sku = row.variant_sku ?? row.sku;
      const key = itemKey(row.product_id, variantId);
      itemRows.set(key, {
        key,
        product_id: row.product_id,
        variant_id: variantId,
        product_name: row.product_name,
        sku,
      });
    }
    return [...itemRows.values()].sort((a, b) => itemLabel(a).localeCompare(itemLabel(b)));
  }, [levels, sourceLocationId]);

  const destinationLocations = locations.filter(
    (location) => String(location.id) !== sourceLocationId,
  );

  async function refreshLevels() {
    setLevels(await api<StockLevel[]>('/stock/levels'));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setFieldErrors({});
    setSuccess('');

    const selectedItem = items.find((item) => item.key === itemSelection);
    const parsedQuantity = Number(quantity);
    if (!selectedItem || !sourceLocationId || !destinationLocationId) {
      setError('Choose an item, source location, and destination location.');
      return;
    }
    if (sourceLocationId === destinationLocationId) {
      setError('Source and destination locations must be different.');
      return;
    }
    if (!Number.isSafeInteger(parsedQuantity) || parsedQuantity <= 0) {
      setFieldErrors({ quantity: 'Enter a positive whole-number quantity.' });
      return;
    }

    setSubmitting(true);
    try {
      await api('/stock/transfers', {
        method: 'POST',
        body: {
          product_id: selectedItem.product_id,
          variant_id: selectedItem.variant_id,
          from_location_id: Number(sourceLocationId),
          to_location_id: Number(destinationLocationId),
          quantity: parsedQuantity,
        },
      });
      setSuccess('Stock transfer completed successfully.');
      setItemSelection('');
      setSourceLocationId(
        canChooseAnySource && user?.role !== 'staff' ? '' : String(user?.location_id ?? ''),
      );
      setDestinationLocationId('');
      setQuantity('');
      try {
        await refreshLevels();
      } catch {
        setError('Transfer succeeded, but availability could not be refreshed. Reload the page.');
      }
    } catch (cause) {
      if (cause instanceof ApiError) {
        setError(cause.message);
        setFieldErrors(cause.fields);
      } else {
        setError('Could not complete the stock transfer. Please try again.');
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <p className="loading">Loading transfer options…</p>;

  return (
    <div className="page">
      <header className="page-header">
        <h1>Stock transfer</h1>
      </header>
      {loadError ? (
        <p role="alert" className="error">
          {loadError}
        </p>
      ) : (
        <>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          {success && <p role="status">{success}</p>}
          <form aria-label="Stock transfer" onSubmit={submit}>
            <FormField label="Source location" error={fieldErrors.from_location_id}>
              {(field) => (
                <select
                  {...field}
                  required
                  value={sourceLocationId}
                  onChange={(event) => {
                    setSourceLocationId(event.target.value);
                    setItemSelection('');
                    setDestinationLocationId('');
                  }}
                >
                  <option value="">Choose a source location</option>
                  {sourceLocations.map((location) => (
                    <option key={location.id} value={location.id}>
                      {location.name}
                    </option>
                  ))}
                </select>
              )}
            </FormField>
            <FormField
              label="Product or variant"
              error={fieldErrors.product_id}
              hint={
                sourceLocationId && items.length === 0
                  ? 'No items with available stock at this source location.'
                  : undefined
              }
            >
              {(field) => (
                <select
                  {...field}
                  required
                  value={itemSelection}
                  disabled={!sourceLocationId || items.length === 0}
                  onChange={(event) => {
                    setItemSelection(event.target.value);
                    setDestinationLocationId('');
                  }}
                >
                  <option value="">Choose a product or variant</option>
                  {items.map((item) => (
                    <option key={item.key} value={item.key}>
                      {itemLabel(item)}
                    </option>
                  ))}
                </select>
              )}
            </FormField>
            <FormField label="Destination location" error={fieldErrors.to_location_id}>
              {(field) => (
                <select
                  {...field}
                  required
                  value={destinationLocationId}
                  disabled={!sourceLocationId || !itemSelection}
                  onChange={(event) => setDestinationLocationId(event.target.value)}
                >
                  <option value="">Choose a destination location</option>
                  {destinationLocations.map((location) => (
                    <option key={location.id} value={location.id}>
                      {location.name}
                    </option>
                  ))}
                </select>
              )}
            </FormField>
            <FormField label="Quantity" error={fieldErrors.quantity}>
              {(field) => (
                <input
                  {...field}
                  type="number"
                  min="1"
                  step="1"
                  required
                  value={quantity}
                  onChange={(event) => setQuantity(event.target.value)}
                />
              )}
            </FormField>
            <button
              type="submit"
              disabled={
                submitting ||
                !sourceLocationId ||
                !itemSelection ||
                !destinationLocationId ||
                !Number.isSafeInteger(Number(quantity)) ||
                Number(quantity) <= 0
              }
            >
              {submitting ? 'Transferring…' : 'Transfer stock'}
            </button>
          </form>
        </>
      )}
    </div>
  );
}
