import { useEffect, useMemo, useState } from 'react';
import { ApiError, api } from '../../api';
import { useAuth } from '../auth';
import { productApi, type Product } from '../product/api';
import { EmptyState, FormField, SearchBox } from '../../shell/components';
import { salesApi, type Availability, type Sale } from './api';

const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' });
const GST_RATE = 18;

type CartLine = Availability & {
  quantity: number;
  discount: number;
  discount_type: 'percentage' | 'amount';
  error?: string;
};

interface Location {
  id: number;
  name: string;
  type: string;
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
  const [submitting, setSubmitting] = useState(false);
  const [idempotencyKey, setIdempotencyKey] = useState(() => crypto.randomUUID());

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
      return [...current, { ...row, quantity: 1, discount: 0, discount_type: 'amount' }];
    });
  }

  function updateLine(index: number, change: Partial<CartLine>) {
    setCart((current) =>
      current.map((line, rowIndex) =>
        rowIndex === index ? { ...line, ...change, error: undefined } : line,
      ),
    );
  }

  async function completeSale() {
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
    } catch (cause: unknown) {
      if (cause instanceof ApiError && cause.status === 409) {
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
  }

  if (sale) {
    return (
      <div className="page">
        <h1>Sale recorded</h1>
        <p>Invoice number: {sale.invoice.invoice_number}</p>
        <p>{new Date(sale.sold_at).toLocaleString()}</p>
        <p>Total: {money.format(Number(sale.total))}</p>
        <button
          type="button"
          onClick={() => {
            setSale(null);
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
            (locationId ? `Location ${locationId}` : '')}
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
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="pos-grid">
        <section>
          <SearchBox onSearch={setQuery} label="Find a product" />
          {loading && <p>Searching...</p>}
          {!loading && query && products.length === 0 && <EmptyState message="No products found" />}
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
                <FormField label="Quantity" error={line.error}>
                  {(control) => (
                    <input
                      {...control}
                      type="number"
                      min="1"
                      max={line.available_quantity}
                      value={line.quantity}
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
