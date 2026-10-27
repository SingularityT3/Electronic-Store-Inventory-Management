import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { ApiError } from '../../api';
import { DataTable, type Column } from '../../shell/components';
import {
  purchasingApi,
  type PurchaseOrder,
  type PurchaseOrderLine,
  type PurchaseOrderReceiptInput,
} from './api';

interface ReceiptDraft {
  quantity_accepted: number;
  quantity_damaged: number;
  quantity_short: number;
  unit_price: string;
  discrepancy_note: string;
  batch_number: string;
  serial_numbers: string;
  damaged_serial_numbers: string;
}

function serials(value: string): string[] {
  return value
    .split(/[\r\n,]/)
    .map((serial) => serial.trim())
    .filter(Boolean);
}

function emptyDraft(line: PurchaseOrderLine): ReceiptDraft {
  return {
    quantity_accepted: 0,
    quantity_damaged: 0,
    quantity_short: 0,
    unit_price: line.unit_price,
    discrepancy_note: '',
    batch_number: '',
    serial_numbers: '',
    damaged_serial_numbers: '',
  };
}

export default function POReceivingPage() {
  const [orders, setOrders] = useState<PurchaseOrder[]>([]);
  const [selected, setSelected] = useState<PurchaseOrder | null>(null);
  const [drafts, setDrafts] = useState<Record<number, ReceiptDraft>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const load = useCallback(async () => {
    const nextOrders = await purchasingApi.receivablePurchaseOrders();
    setOrders(nextOrders);
  }, []);

  useEffect(() => {
    let current = true;
    purchasingApi
      .receivablePurchaseOrders()
      .then((nextOrders) => current && setOrders(nextOrders))
      .catch(
        (cause: unknown) =>
          current &&
          setError(cause instanceof ApiError ? cause.message : 'Could not load receivable orders.'),
      )
      .finally(() => current && setLoading(false));
    return () => {
      current = false;
    };
  }, []);

  function chooseOrder(order: PurchaseOrder) {
    setSelected(order);
    setDrafts(Object.fromEntries(order.lines.map((line) => [line.id, emptyDraft(line)])));
    setError('');
    setMessage('');
  }

  function updateDraft(lineId: number, field: keyof ReceiptDraft, value: string) {
    setDrafts((current) => ({
      ...current,
      [lineId]: {
        ...current[lineId],
        [field]:
          field === 'quantity_accepted' ||
          field === 'quantity_damaged' ||
          field === 'quantity_short'
            ? Number(value)
            : value,
      },
    }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    setError('');
    setMessage('');
    const lines: PurchaseOrderReceiptInput['lines'] = [];
    for (const line of selected.lines) {
      const draft = drafts[line.id];
      const quantity = draft.quantity_accepted + draft.quantity_damaged + draft.quantity_short;
      if (!quantity) continue;
      if ((draft.quantity_damaged || draft.quantity_short) && !draft.discrepancy_note.trim()) {
        setError(`Add a discrepancy note for ${line.sku}.`);
        return;
      }
      lines.push({
        po_line_id: line.id,
        quantity_accepted: draft.quantity_accepted,
        quantity_damaged: draft.quantity_damaged,
        quantity_short: draft.quantity_short,
        unit_price: draft.unit_price,
        discrepancy_note: draft.discrepancy_note.trim() || null,
        ...(line.tracking_mode === 'batch' && draft.batch_number.trim()
          ? { batch_number: draft.batch_number.trim() }
          : {}),
        ...(line.tracking_mode === 'serial'
          ? {
              serial_numbers: serials(draft.serial_numbers),
              damaged_serial_numbers: serials(draft.damaged_serial_numbers),
            }
          : {}),
      });
    }
    if (!lines.length) {
      setError('Enter a received, damaged, or short quantity for at least one line.');
      return;
    }

    setSaving(true);
    try {
      const updated = await purchasingApi.receivePurchaseOrder(selected.id, {
        notes: null,
        lines,
      });
      setSelected(updated);
      setDrafts(Object.fromEntries(updated.lines.map((line) => [line.id, emptyDraft(line)])));
      await load();
      setMessage(`Receipt recorded for ${updated.po_number}.`);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not record receipt.');
    } finally {
      setSaving(false);
    }
  }

  const orderColumns: Column<PurchaseOrder>[] = [
    {
      header: 'PO number',
      cell: (order) => (
        <button type="button" onClick={() => chooseOrder(order)}>
          {order.po_number}
        </button>
      ),
    },
    { header: 'Supplier', cell: (order) => order.supplier_name },
    { header: 'Status', cell: (order) => order.status.replaceAll('_', ' ') },
    { header: 'Location', cell: (order) => order.location_id },
  ];

  const lineColumns: Column<PurchaseOrderLine>[] = [
    { header: 'Product / SKU', cell: (line) => `${line.product_name} (${line.sku})` },
    { header: 'Outstanding', cell: (line) => line.quantity_outstanding },
    {
      header: 'Accepted',
      cell: (line) => (
        <input
          aria-label={`Accepted ${line.sku}`}
          type="number"
          min="0"
          max={line.quantity_outstanding}
          step="1"
          disabled={!line.quantity_outstanding}
          value={drafts[line.id]?.quantity_accepted ?? 0}
          onChange={(event) => updateDraft(line.id, 'quantity_accepted', event.target.value)}
        />
      ),
    },
    {
      header: 'Damaged',
      cell: (line) => (
        <input
          aria-label={`Damaged ${line.sku}`}
          type="number"
          min="0"
          max={line.quantity_outstanding}
          step="1"
          disabled={!line.quantity_outstanding}
          value={drafts[line.id]?.quantity_damaged ?? 0}
          onChange={(event) => updateDraft(line.id, 'quantity_damaged', event.target.value)}
        />
      ),
    },
    {
      header: 'Short',
      cell: (line) => (
        <input
          aria-label={`Short ${line.sku}`}
          type="number"
          min="0"
          max={line.quantity_outstanding}
          step="1"
          disabled={!line.quantity_outstanding}
          value={drafts[line.id]?.quantity_short ?? 0}
          onChange={(event) => updateDraft(line.id, 'quantity_short', event.target.value)}
        />
      ),
    },
    {
      header: 'Receipt unit price',
      cell: (line) => (
        <input
          aria-label={`Receipt unit price ${line.sku}`}
          type="number"
          min="0"
          step="0.01"
          disabled={!line.quantity_outstanding}
          value={drafts[line.id]?.unit_price ?? line.unit_price}
          onChange={(event) => updateDraft(line.id, 'unit_price', event.target.value)}
        />
      ),
    },
    {
      header: 'Batch / serial details',
      cell: (line) => {
        const draft = drafts[line.id];
        if (line.tracking_mode === 'batch') {
          return (
            <input
              aria-label={`Batch number ${line.sku}`}
              disabled={!line.quantity_outstanding}
              value={draft?.batch_number ?? ''}
              onChange={(event) => updateDraft(line.id, 'batch_number', event.target.value)}
            />
          );
        }
        if (line.tracking_mode === 'serial') {
          return (
            <div>
              <textarea
                aria-label={`Accepted serial numbers ${line.sku}`}
                disabled={!line.quantity_outstanding}
                value={draft?.serial_numbers ?? ''}
                onChange={(event) => updateDraft(line.id, 'serial_numbers', event.target.value)}
              />
              <textarea
                aria-label={`Damaged serial numbers ${line.sku}`}
                disabled={!line.quantity_outstanding}
                value={draft?.damaged_serial_numbers ?? ''}
                onChange={(event) =>
                  updateDraft(line.id, 'damaged_serial_numbers', event.target.value)
                }
              />
            </div>
          );
        }
        return 'Untracked';
      },
    },
    {
      header: 'Discrepancy note',
      cell: (line) => (
        <input
          aria-label={`Discrepancy note ${line.sku}`}
          disabled={!line.quantity_outstanding}
          value={drafts[line.id]?.discrepancy_note ?? ''}
          onChange={(event) => updateDraft(line.id, 'discrepancy_note', event.target.value)}
        />
      ),
    },
  ];

  if (loading) return <p className="loading">Loading receivable purchase orders…</p>;

  return (
    <div className="page">
      <h1>PO receiving</h1>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {message && <p role="status">{message}</p>}
      <DataTable
        caption="Receivable purchase orders"
        columns={orderColumns}
        rows={orders}
        rowKey={(order) => order.id}
        emptyMessage="No purchase orders are waiting to be received."
      />
      {selected && (
        <section>
          <h2>
            Receive {selected.po_number} · {selected.status.replaceAll('_', ' ')}
          </h2>
          <form aria-label="Purchase order receipt" onSubmit={submit}>
            <DataTable
              caption="Purchase order receipt lines"
              columns={lineColumns}
              rows={selected.lines}
              rowKey={(line) => line.id}
              emptyMessage="This purchase order has no lines."
            />
            <button type="submit" disabled={saving}>
              {saving ? 'Recording receipt…' : 'Record receipt'}
            </button>
          </form>
        </section>
      )}
    </div>
  );
}
