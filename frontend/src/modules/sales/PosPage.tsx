import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ApiError, api } from '../../api';
import { useAuth } from '../auth';
import { productApi, type Product } from '../product/api';
import { EmptyState, FormField, SearchBox } from '../../shell/components';
import { salesApi, type Availability, type DocumentContent, type Sale } from './api';
import DocumentView from './DocumentView';

const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' });
const GST_RATE = 18;

type CartLine = Availability & {
  quantity: number;
  /** Serial-tracked items are sold unit by unit (FR-2.5): one serial number per unit. */
  tracking_mode: Product['tracking_mode'];
  serials: string;
  discount: number;
  discount_type: 'percentage' | 'amount';
  error?: string;
};

interface Location {
  id: number;
  name: string;
  type: string;
}

function serialList(value: string): string[] {
  return value
    .split(/[\s,]+/)
    .map((serial) => serial.trim())
    .filter(Boolean);
}

function amount(value: number) {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

function attributes(row: Availability) {
  return row.variant_attributes ? Object.values(row.variant_attributes).join(' / ') : '';
}

export default function PosPage() {
  const { user } = useAuth();
  const canChooseLocation = user?.role === 'admin' || user?.role === 'manager';
  const [locations, setLocations] = useState<Location[]>([]);
  const [locationId, setLocationId] = useState('');
  const [products, setProducts] = useState<Product[]>([]);
  const [availability, setAvailability] = useState<Availability[]>([]);
  const [cart, setCart] = useState<CartLine[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [paymentMethod, setPaymentMethod] = useState('cash');
  const [paymentAmount, setPaymentAmount] = useState('');
  const [received, setReceived] = useState('');
  const [reference, setReference] = useState('');
  const [sale, setSale] = useState<Sale | null>(null);
  const [invoiceContent, setInvoiceContent] = useState<DocumentContent | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [idempotencyKey, setIdempotencyKey] = useState(() => crypto.randomUUID());
  const searchInputRef = useRef<HTMLInputElement>(null);
  const [searchResetKey, setSearchResetKey] = useState(0);
  const autoAddedKey = useRef('');

  useEffect(() => {
    if (!canChooseLocation) {
      if (user?.location_id) setLocationId(String(user.location_id));
      return;
    }
    api<Location[]>('/stock/locations')
      .then(setLocations)
      .catch((cause: unknown) =>
        setError(cause instanceof ApiError ? cause.message : 'Could not load locations.'),
      );
  }, [canChooseLocation, user?.location_id]);

  useEffect(() => {
    if (!locationId || !query.trim()) {
      setProducts([]);
      setAvailability([]);
      return;
    }
    let current = true;
    setLoading(true);
    productApi
      .list(1, 20, { q: query })
      .then(async (result) => {
        const rows = await salesApi.availability(
          Number(locationId),
          result.items.map((item) => item.id),
        );
        const variantPrices = new Map<number, string>();
        await Promise.all(
          result.items
            .filter((item) => item.variant_count > 0)
            .map(async (item) => {
              const variants = await productApi.variants(item.id);
              variants.forEach((variant) => variantPrices.set(variant.id, variant.effective_price));
            }),
        );
        if (current) {
          setProducts(result.items);
          setAvailability(
            rows.map((row) => ({
              ...row,
              unit_price: row.variant_id
                ? (variantPrices.get(row.variant_id) ?? '0')
                : (result.items.find((item) => item.id === row.product_id)?.price ?? '0'),
              tracking_mode: result.items.find((item) => item.id === row.product_id)?.tracking_mode,
            })),
          );
        }
      })
      .catch(
        (cause: unknown) =>
          current &&
          setError(cause instanceof ApiError ? cause.message : 'Could not search products.'),
      )
      .finally(() => current && setLoading(false));
    return () => {
      current = false;
    };
  }, [locationId, query]);

  useEffect(() => {
    if (!query || loading || products.length !== 1) return;
    const rows = availability.filter((row) => row.product_id === products[0].id);
    const normalized = query.trim().toLowerCase();
    const exactRows = rows.filter(
      (row) =>
        row.sku.toLowerCase() === normalized || row.variant_sku?.toLowerCase() === normalized,
    );
    const row = exactRows.length === 1 ? exactRows[0] : rows.length === 1 ? rows[0] : null;
    if (!row) return;
    const key = `${query}:${row.product_id}:${row.variant_id ?? ''}`;
    if (autoAddedKey.current === key) return;
    autoAddedKey.current = key;
    add(row);
    setQuery('');
    setSearchResetKey((current) => current + 1);
    requestAnimationFrame(() => searchInputRef.current?.focus());
  }, [availability, loading, products, query]);

  const subtotal = useMemo(
    () => amount(cart.reduce((sum, line) => sum + Number(line.unit_price) * line.quantity, 0)),
    [cart],
  );
  const discount = useMemo(
    () =>
      amount(
        cart.reduce((sum, line) => {
          const gross = Number(line.unit_price) * line.quantity;
          return (
            sum +
            (line.discount_type === 'percentage' ? (gross * line.discount) / 100 : line.discount)
          );
        }, 0),
      ),
    [cart],
  );
  const tax = amount(((subtotal - discount) * GST_RATE) / 100);
  const total = amount(subtotal - discount + tax);
  const change = paymentMethod === 'cash' ? Math.max(0, Number(received || 0) - total) : 0;

  function add(row: Availability) {
    setCart((current) => {
      const found = current.find(
        (line) => line.product_id === row.product_id && line.variant_id === row.variant_id,
      );
      if (found) {
        return current.map((line) =>
          line === found
            ? {
                ...line,
                quantity: Math.min(line.quantity + 1, row.available_quantity),
                error: undefined,
              }
            : line,
        );
      }
      return [
        ...current,
        {
          ...row,
          quantity: 1,
          discount: 0,
          discount_type: 'amount',
          tracking_mode: row.tracking_mode ?? 'untracked',
          serials: '',
        },
      ];
    });
  }

  function updateLine(index: number, change: Partial<CartLine>) {
    setCart((current) =>
      current.map((line, rowIndex) =>
        rowIndex === index ? { ...line, ...change, error: undefined } : line,
      ),
    );
  }

  const completeSale = useCallback(async () => {
    if (submitting || !locationId) return;
    setSubmitting(true);
    setError('');
    try {
      const result = await salesApi.create({
        location_id: Number(locationId),
        lines: cart.map((line) => ({
          product_id: line.product_id,
          variant_id: line.variant_id,
          quantity: line.quantity,
          discount: line.discount,
          discount_type: line.discount_type,
          ...(line.tracking_mode === 'serial' ? { serial_numbers: serialList(line.serials) } : {}),
        })),
        payments: [
          {
            method: paymentMethod,
            amount: Number(paymentAmount || total),
            reference: reference || undefined,
          },
        ],
        idempotency_key: idempotencyKey,
      });
      setSale(result);
      setInvoiceContent(result.invoice.content);
    } catch (cause: unknown) {
      // 409: stock problems; 422: e.g. a serial number that is not in stock. Both name the line.
      if (cause instanceof ApiError && (cause.status === 409 || cause.status === 422)) {
        const messages = cause.fields;
        setCart((current) =>
          current.map((line) => {
            const key = `${line.product_id}:${line.variant_id ?? ''}`;
            const failure = messages[key];
            return failure ? { ...line, error: failure } : line;
          }),
        );
        setError(cause.message);
      } else {
        setError(cause instanceof ApiError ? cause.message : 'Could not record sale.');
      }
    } finally {
      setSubmitting(false);
    }
  }, [
    cart,
    idempotencyKey,
    locationId,
    paymentAmount,
    paymentMethod,
    reference,
    submitting,
    total,
  ]);

  useEffect(() => {
    function handleShortcut(event: KeyboardEvent) {
      if (event.altKey && event.key.toLowerCase() === 's') {
        event.preventDefault();
        searchInputRef.current?.focus();
      }
      if (event.altKey && event.key === 'Enter' && cart.length > 0) {
        event.preventDefault();
        void completeSale();
      }
    }
    window.addEventListener('keydown', handleShortcut);
    return () => window.removeEventListener('keydown', handleShortcut);
  }, [cart.length, completeSale]);

  if (sale) {
    return (
      <div className="page">
        <h1>Sale recorded</h1>
        <p>{new Date(sale.sold_at).toLocaleString()}</p>
        <p>Total: {money.format(Number(sale.total))}</p>
        {invoiceContent ? (
          <DocumentView
            document={invoiceContent}
            pdfUrl={`/sales/invoices/${encodeURIComponent(sale.invoice.invoice_label)}/pdf`}
          />
        ) : (
          <p role="status">Loading invoice…</p>
        )}
        <button
          type="button"
          onClick={() => {
            setSale(null);
            setInvoiceContent(null);
            setCart([]);
            setIdempotencyKey(crypto.randomUUID());
            setPaymentAmount('');
            setReceived('');
          }}
        >
          New sale
        </button>
      </div>
    );
  }

  return (
    <div className="page pos-page">
      <header className="page-header">
        <h1>Record sale</h1>
        <p>
          {locations.find((location) => String(location.id) === locationId)?.name ??
            availability.find((row) => String(row.location_id) === locationId)?.location_name ??
            (locationId ? 'Your assigned location' : '')}
        </p>
      </header>
      {canChooseLocation && (
        <FormField label="Sale location">
          {(control) => (
            <select
              {...control}
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
      )}
      {error && (
        <p role="alert" aria-live="assertive" className="error">
          {error}
        </p>
      )}
      <div className="pos-grid">
        <section>
          <SearchBox
            onSearch={setQuery}
            label="Find a product"
            autoFocus
            inputRef={searchInputRef}
            resetKey={searchResetKey}
          />
          <p className="form-hint">
            Shortcuts: Alt+S focuses search; Alt+Enter completes the sale.
          </p>
          {loading && <p>Searching...</p>}
          {!loading && query && products.length === 0 && <EmptyState message="No products found" />}
          {!loading && query && products.length > 1 && (
            <p role="status">Several products match. Choose the intended product below.</p>
          )}
          {products.map((product) => {
            const rows = availability.filter((row) => row.product_id === product.id);
            return (
              <div key={product.id} className="pos-result">
                <strong>{product.name}</strong> <span>{product.sku}</span>
                {rows.map((row) => (
                  <button
                    type="button"
                    key={`${row.product_id}-${row.variant_id ?? 'base'}`}
                    onClick={() => add(row)}
                  >
                    {row.variant_id ? `${attributes(row)} (${row.variant_sku})` : product.name} —{' '}
                    {money.format(Number(row.unit_price))} — {row.available_quantity} available
                  </button>
                ))}
              </div>
            );
          })}
        </section>
        <section>
          <h2>Cart</h2>
          {cart.length === 0 ? (
            <EmptyState message="Cart is empty" />
          ) : (
            cart.map((line, index) => (
              <div
                key={`${line.product_id}-${line.variant_id ?? 'base'}`}
                className="pos-cart-line"
              >
                <strong>
                  {line.product_name} {line.variant_sku && `(${line.variant_sku})`}
                </strong>
                <span>{money.format(Number(line.unit_price))}</span>
                {line.tracking_mode === 'serial' && (
                  <FormField
                    label="Serial numbers"
                    hint="Scan or type the serial number of each unit, one per line."
                  >
                    {(control) => (
                      <textarea
                        {...control}
                        rows={2}
                        value={line.serials}
                        onChange={(event) =>
                          updateLine(index, {
                            serials: event.target.value,
                            quantity: Math.max(serialList(event.target.value).length, 1),
                          })
                        }
                      />
                    )}
                  </FormField>
                )}
                <FormField label="Quantity" error={line.error}>
                  {(control) => (
                    <input
                      {...control}
                      type="number"
                      min="1"
                      max={line.available_quantity}
                      value={line.quantity}
                      readOnly={line.tracking_mode === 'serial'}
                      onChange={(event) =>
                        updateLine(index, { quantity: Number(event.target.value) })
                      }
                    />
                  )}
                </FormField>
                <FormField label="Discount">
                  {(control) => (
                    <input
                      {...control}
                      type="number"
                      min="0"
                      value={line.discount}
                      onChange={(event) =>
                        updateLine(index, { discount: Number(event.target.value) })
                      }
                    />
                  )}
                </FormField>
                <select
                  aria-label="Discount type"
                  value={line.discount_type}
                  onChange={(event) =>
                    updateLine(index, {
                      discount_type: event.target.value as CartLine['discount_type'],
                    })
                  }
                >
                  <option value="amount">₹ amount</option>
                  <option value="percentage">%</option>
                </select>
                <button
                  type="button"
                  onClick={() =>
                    setCart((current) => current.filter((_, rowIndex) => rowIndex !== index))
                  }
                >
                  Remove
                </button>
              </div>
            ))
          )}
          <div className="pos-totals">
            <p>Subtotal: {money.format(subtotal)}</p>
            <p>Discount: {money.format(discount)}</p>
            <p>GST: {money.format(tax)}</p>
            <strong>Grand total: {money.format(total)}</strong>
          </div>
          <h2>Payment</h2>
          <FormField label="Method">
            {(control) => (
              <select
                {...control}
                value={paymentMethod}
                onChange={(event) => setPaymentMethod(event.target.value)}
              >
                <option value="cash">Cash</option>
                <option value="card">Card</option>
                <option value="upi">UPI</option>
                <option value="other">Other</option>
              </select>
            )}
          </FormField>
          <FormField label="Amount">
            {(control) => (
              <input
                {...control}
                type="number"
                step="0.01"
                value={paymentAmount || total}
                onChange={(event) => setPaymentAmount(event.target.value)}
              />
            )}
          </FormField>
          {paymentMethod === 'cash' && (
            <FormField label="Received">
              {(control) => (
                <input
                  {...control}
                  type="number"
                  step="0.01"
                  value={received}
                  onChange={(event) => setReceived(event.target.value)}
                />
              )}
            </FormField>
          )}
          {paymentMethod === 'cash' && <p>Change due: {money.format(change)}</p>}
          <FormField label="Reference">
            {(control) => (
              <input
                {...control}
                value={reference}
                onChange={(event) => setReference(event.target.value)}
              />
            )}
          </FormField>
          <button
            type="button"
            disabled={submitting || cart.length === 0 || !locationId}
            onClick={completeSale}
          >
            Complete sale
          </button>
        </section>
      </div>
    </div>
  );
}
