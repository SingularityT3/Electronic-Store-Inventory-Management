import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ApiError, api } from '../../api';
import { ConfirmDialog, DataTable, FormField, type Column } from '../../shell/components';
import {
  purchasingApi,
  type PurchaseOrder,
  type PurchaseOrderInput,
  type PurchaseOrderLineInput,
  type Supplier,
  type SupplierProduct,
} from './api';

interface Location {
  id: number;
  name: string;
  type: string;
}

interface DraftLine extends PurchaseOrderLineInput {
  key: string;
  product_name: string;
  sku: string;
}

interface ReorderPrefill {
  product_id: number;
  variant_id: number | null;
  product_name: string;
  sku: string;
  quantity: number;
  location_id: number;
}

function currency(value: string | number): string {
  return Number(value).toFixed(2);
}

export default function PurchaseOrdersPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const reorderPrefill = useMemo<ReorderPrefill | null>(() => {
    const productId = Number(searchParams.get('product_id'));
    const quantity = Number(searchParams.get('quantity'));
    const locationId = Number(searchParams.get('location_id'));
    const rawVariantId = searchParams.get('variant_id');
    const variantId = rawVariantId === null ? null : Number(rawVariantId);
    if (
      !Number.isSafeInteger(productId) ||
      productId <= 0 ||
      !Number.isSafeInteger(quantity) ||
      quantity <= 0 ||
      !Number.isSafeInteger(locationId) ||
      locationId <= 0 ||
      (variantId !== null && (!Number.isSafeInteger(variantId) || variantId <= 0))
    ) {
      return null;
    }
    return {
      product_id: productId,
      variant_id: variantId,
      product_name: searchParams.get('product_name') ?? 'Reorder item',
      sku: searchParams.get('variant_sku') ?? searchParams.get('sku') ?? '',
      quantity,
      location_id: locationId,
    };
  }, [searchParams]);

  const [orders, setOrders] = useState<PurchaseOrder[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);
  const [catalog, setCatalog] = useState<SupplierProduct[]>([]);
  const [catalogLoadedFor, setCatalogLoadedFor] = useState('');
  const [selected, setSelected] = useState<PurchaseOrder | null>(null);
  const [supplierId, setSupplierId] = useState('');
  const [locationId, setLocationId] = useState(() =>
    reorderPrefill ? String(reorderPrefill.location_id) : '',
  );
  const [deliveryDate, setDeliveryDate] = useState('');
  const [notes, setNotes] = useState('');
  const [lines, setLines] = useState<DraftLine[]>(() =>
    reorderPrefill
      ? [
          {
            key: 'reorder-prefill',
            product_id: reorderPrefill.product_id,
            variant_id: reorderPrefill.variant_id,
            product_name: reorderPrefill.product_name,
            sku: reorderPrefill.sku,
            quantity_ordered: reorderPrefill.quantity,
            unit_price: '',
          },
        ]
      : [],
  );
  const [catalogChoice, setCatalogChoice] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState('');
  const [confirmCancel, setConfirmCancel] = useState(false);

  const load = useCallback(async () => {
    const [nextOrders, nextSuppliers, nextLocations] = await Promise.all([
      purchasingApi.purchaseOrders(),
      purchasingApi.suppliers(true),
      api<Location[]>('/stock/locations'),
    ]);
    setOrders(nextOrders);
    setSuppliers(nextSuppliers);
    setLocations(nextLocations);
  }, []);

  useEffect(() => {
    let current = true;
    Promise.all([
      purchasingApi.purchaseOrders(),
      purchasingApi.suppliers(true),
      api<Location[]>('/stock/locations'),
    ])
      .then(([nextOrders, nextSuppliers, nextLocations]) => {
        if (!current) return;
        setOrders(nextOrders);
        setSuppliers(nextSuppliers);
        setLocations(nextLocations);
      })
      .catch(
        (cause: unknown) =>
          current &&
          setError(cause instanceof ApiError ? cause.message : 'Could not load purchase orders.'),
      )
      .finally(() => current && setLoading(false));
    return () => {
      current = false;
    };
  }, []);

  useEffect(() => {
    if (!supplierId) {
      setCatalog([]);
      setCatalogLoadedFor('');
      return;
    }
    let current = true;
    setCatalog([]);
    setCatalogLoadedFor('');
    purchasingApi
      .supplierProducts(Number(supplierId))
      .then((rows) => {
        if (!current) return;
        setCatalog(rows);
        setCatalogLoadedFor(supplierId);
      })
      .catch((cause: unknown) => {
        if (current) {
          setError(cause instanceof ApiError ? cause.message : 'Could not load supplier catalog.');
        }
      });
    return () => {
      current = false;
    };
  }, [supplierId]);

  useEffect(() => {
    if (!reorderPrefill || selected || !supplierId || catalogLoadedFor !== supplierId) {
      return;
    }
    const catalogItem = catalog.find(
      (item) =>
        item.product_id === reorderPrefill.product_id &&
        item.variant_id === reorderPrefill.variant_id,
    );
    if (!catalogItem) {
      setError('Selected supplier does not have this product or variant in its catalog.');
      return;
    }
    setError('');
    setLines((current) =>
      current.map((line) =>
        line.key === 'reorder-prefill'
          ? {
              ...line,
              product_name: catalogItem.product_name,
              sku: catalogItem.product_sku,
              unit_price: catalogItem.supplier_price,
            }
          : line,
      ),
    );
  }, [catalog, catalogLoadedFor, reorderPrefill, selected, supplierId]);

  const totalCents = useMemo(
    () =>
      lines.reduce(
        (sum, line) => sum + line.quantity_ordered * Math.round(Number(line.unit_price) * 100),
        0,
      ),
    [lines],
  );
  const canEdit = selected === null || selected.status === 'draft';

  function clearForm() {
    setSearchParams({}, { replace: true });
    setSelected(null);
    setSupplierId('');
    setLocationId('');
    setDeliveryDate('');
    setNotes('');
    setLines([]);
    setCatalogChoice('');
    setError('');
    setFieldErrors({});
    setMessage('');
  }

  async function selectOrder(row: PurchaseOrder) {
    setError('');
    setMessage('');
    try {
      const order = await purchasingApi.purchaseOrder(row.id);
      setSelected(order);
      setSupplierId(String(order.supplier_id));
      setLocationId(String(order.location_id));
      setDeliveryDate(order.expected_delivery_date ?? '');
      setNotes(order.notes ?? '');
      setLines(
        order.lines.map((line) => ({
          key: String(line.id),
          product_id: line.product_id,
          variant_id: line.variant_id,
          product_name: line.product_name,
          sku: line.sku,
          quantity_ordered: line.quantity_ordered,
          unit_price: line.unit_price,
        })),
      );
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not load purchase order.');
    }
  }

  function addCatalogLine() {
    const entry = catalog.find((item) => String(item.id) === catalogChoice);
    if (!entry) return;
    if (
      lines.some(
        (line) => line.product_id === entry.product_id && line.variant_id === entry.variant_id,
      )
    ) {
      setError('This product or variant is already in the purchase order.');
      return;
    }
    setError('');
    setLines((current) => [
      ...current,
      {
        key: `new-${entry.id}-${Date.now()}`,
        product_id: entry.product_id,
        variant_id: entry.variant_id,
        product_name: entry.product_name,
        sku: entry.product_sku,
        quantity_ordered: 1,
        unit_price: entry.supplier_price,
      },
    ]);
    setCatalogChoice('');
  }

  function updateLine(key: string, field: 'quantity_ordered' | 'unit_price', value: string) {
    setLines((current) =>
      current.map((line) =>
        line.key === key
          ? {
              ...line,
              [field]: field === 'quantity_ordered' ? Number(value) : value,
            }
          : line,
      ),
    );
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setMessage('');
    setFieldErrors({});
    if (lines.length === 0) {
      setError('Add at least one supplier catalog item.');
      return;
    }
    if (
      lines.some(
        (line) => !Number.isSafeInteger(line.quantity_ordered) || line.quantity_ordered <= 0,
      )
    ) {
      setFieldErrors({ quantity_ordered: 'Quantity must be a positive whole number.' });
      return;
    }
    if (
      lines.some((line) => !Number.isFinite(Number(line.unit_price)) || Number(line.unit_price) < 0)
    ) {
      setFieldErrors({ unit_price: 'Unit price cannot be negative.' });
      return;
    }
    if (lines.some((line) => line.unit_price.trim() === '')) {
      setFieldErrors({ unit_price: 'Choose a supplier catalog price for each line.' });
      return;
    }
    const body: PurchaseOrderInput = {
      supplier_id: Number(supplierId),
      location_id: Number(locationId),
      expected_delivery_date: deliveryDate,
      notes: notes || null,
      lines: lines.map(({ product_id, variant_id, quantity_ordered, unit_price }) => ({
        product_id,
        variant_id,
        quantity_ordered,
        unit_price: currency(unit_price),
      })),
    };
    setSaving(true);
    try {
      const saved = selected
        ? await purchasingApi.updatePurchaseOrder(selected.id, body)
        : await purchasingApi.createPurchaseOrder(body);
      setSelected(saved);
      setSupplierId(String(saved.supplier_id));
      setLocationId(String(saved.location_id));
      setLines(
        saved.lines.map((line) => ({
          key: String(line.id),
          product_id: line.product_id,
          variant_id: line.variant_id,
          product_name: line.product_name,
          sku: line.sku,
          quantity_ordered: line.quantity_ordered,
          unit_price: line.unit_price,
        })),
      );
      await load();
      setMessage(selected ? 'Draft purchase order updated.' : 'Draft purchase order created.');
    } catch (cause) {
      if (cause instanceof ApiError) {
        setError(cause.message);
        setFieldErrors(cause.fields);
      } else {
        setError('Could not save purchase order.');
      }
    } finally {
      setSaving(false);
    }
  }

  async function submitOrder() {
    if (!selected) return;
    setError('');
    try {
      const updated = await purchasingApi.submitPurchaseOrder(selected.id);
      setSelected(updated);
      await load();
      setMessage('Purchase order submitted.');
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not submit purchase order.');
    }
  }

  async function cancelOrder() {
    if (!selected) return;
    setError('');
    try {
      const updated = await purchasingApi.cancelPurchaseOrder(selected.id);
      setSelected(updated);
      setConfirmCancel(false);
      await load();
      setMessage('Purchase order cancelled.');
    } catch (cause) {
      setConfirmCancel(false);
      setError(cause instanceof ApiError ? cause.message : 'Could not cancel purchase order.');
    }
  }

  const columns: Column<PurchaseOrder>[] = [
    {
      header: 'PO number',
      cell: (order) => (
        <button type="button" onClick={() => selectOrder(order)}>
          {order.po_number}
        </button>
      ),
    },
    { header: 'Supplier', cell: (order) => order.supplier_name },
    { header: 'Status', cell: (order) => order.status.replaceAll('_', ' ') },
    { header: 'Total', cell: (order) => currency(order.total) },
    { header: 'Expected delivery', cell: (order) => order.expected_delivery_date ?? '—' },
  ];

  if (loading) return <p className="loading">Loading purchase orders…</p>;

  return (
    <div className="page">
      <header className="page-header">
        <h1>Purchase orders</h1>
        <button type="button" onClick={clearForm}>
          New purchase order
        </button>
      </header>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {message && <p role="status">{message}</p>}
      <DataTable
        caption="Purchase orders"
        columns={columns}
        rows={orders}
        rowKey={(order) => order.id}
        emptyMessage="No purchase orders found."
      />
      <section>
        <h2>{selected ? `${selected.po_number} · ${selected.status}` : 'Create purchase order'}</h2>
        <form aria-label="Purchase order" onSubmit={save}>
          <FormField label="Supplier" error={fieldErrors.supplier_id}>
            {(props) => (
              <select
                {...props}
                required
                disabled={!canEdit}
                value={supplierId}
                onChange={(event) => {
                  setSupplierId(event.target.value);
                  setError('');
                  setLines((current) =>
                    current
                      .filter((line) => line.key === 'reorder-prefill')
                      .map((line) => ({ ...line, unit_price: '' })),
                  );
                }}
              >
                <option value="">Choose an active supplier</option>
                {suppliers
                  .filter((supplier) => supplier.is_active)
                  .map((supplier) => (
                    <option key={supplier.id} value={supplier.id}>
                      {supplier.name}
                    </option>
                  ))}
              </select>
            )}
          </FormField>
          {reorderPrefill && !supplierId && canEdit && (
            <p>
              Reorder {reorderPrefill.quantity} unit(s) of {reorderPrefill.product_name}. Choose a
              supplier that carries this item to load its catalog price.
            </p>
          )}
          <FormField label="Receiving location" error={fieldErrors.location_id}>
            {(props) => (
              <select
                {...props}
                required
                disabled={!canEdit}
                value={locationId}
                onChange={(event) => setLocationId(event.target.value)}
              >
                <option value="">Choose a location</option>
                {locations.map((location) => (
                  <option key={location.id} value={location.id}>
                    {location.name}
                  </option>
                ))}
              </select>
            )}
          </FormField>
          <FormField label="Expected delivery date" error={fieldErrors.expected_delivery_date}>
            {(props) => (
              <input
                {...props}
                type="date"
                required
                disabled={!canEdit}
                value={deliveryDate}
                onChange={(event) => setDeliveryDate(event.target.value)}
              />
            )}
          </FormField>
          <FormField label="Notes" error={fieldErrors.notes}>
            {(props) => (
              <textarea
                {...props}
                disabled={!canEdit}
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
              />
            )}
          </FormField>
          {canEdit && (
            <div className="form-field">
              <label htmlFor="catalog-item">Supplier catalog item</label>
              <select
                id="catalog-item"
                value={catalogChoice}
                disabled={!supplierId}
                onChange={(event) => setCatalogChoice(event.target.value)}
              >
                <option value="">Choose a product or variant</option>
                {catalog.map((entry) => (
                  <option key={entry.id} value={entry.id}>
                    {entry.product_name} ({entry.product_sku}) — {entry.supplier_price}
                  </option>
                ))}
              </select>
              <button type="button" disabled={!catalogChoice} onClick={addCatalogLine}>
                Add line
              </button>
            </div>
          )}
          <DataTable
            caption="Purchase order lines"
            columns={[
              { header: 'Product / variant', cell: (line) => `${line.product_name} (${line.sku})` },
              {
                header: 'Quantity',
                cell: (line) =>
                  canEdit ? (
                    <input
                      aria-label={`Quantity ${line.sku}`}
                      type="number"
                      min="1"
                      step="1"
                      value={line.quantity_ordered}
                      onChange={(event) =>
                        updateLine(line.key, 'quantity_ordered', event.target.value)
                      }
                    />
                  ) : (
                    line.quantity_ordered
                  ),
              },
              {
                header: 'Agreed unit price',
                cell: (line) =>
                  canEdit ? (
                    <input
                      aria-label={`Unit price ${line.sku}`}
                      type="number"
                      min="0"
                      step="0.01"
                      value={line.unit_price}
                      onChange={(event) => updateLine(line.key, 'unit_price', event.target.value)}
                    />
                  ) : (
                    line.unit_price
                  ),
              },
              {
                header: 'Line total',
                cell: (line) =>
                  currency(
                    (line.quantity_ordered * Math.round(Number(line.unit_price) * 100)) / 100,
                  ),
              },
              ...(canEdit
                ? [
                    {
                      header: 'Action',
                      cell: (line: DraftLine) => (
                        <button
                          type="button"
                          onClick={() =>
                            setLines((current) => current.filter((item) => item.key !== line.key))
                          }
                        >
                          Remove
                        </button>
                      ),
                    },
                  ]
                : []),
            ]}
            rows={lines}
            rowKey={(line) => line.key}
            emptyMessage="Add products from the selected supplier catalog."
          />
          <p>
            Order total: <strong>{currency(totalCents / 100)}</strong>
          </p>
          {canEdit && (
            <button
              type="submit"
              disabled={
                saving ||
                !supplierId ||
                !locationId ||
                !deliveryDate ||
                (reorderPrefill !== null &&
                  lines.some((line) => line.key === 'reorder-prefill' && !line.unit_price))
              }
            >
              {saving ? 'Saving…' : selected ? 'Save draft' : 'Create draft'}
            </button>
          )}
          {selected?.status === 'draft' && (
            <button type="button" onClick={submitOrder}>
              Submit purchase order
            </button>
          )}
          {selected && ['draft', 'submitted'].includes(selected.status) && (
            <button type="button" onClick={() => setConfirmCancel(true)}>
              Cancel purchase order
            </button>
          )}
        </form>
      </section>
      <ConfirmDialog
        open={confirmCancel}
        title="Cancel purchase order"
        message={`Cancel ${selected?.po_number ?? 'this purchase order'}?`}
        confirmLabel="Cancel purchase order"
        onConfirm={cancelOrder}
        onCancel={() => setConfirmCancel(false)}
      />
    </div>
  );
}
