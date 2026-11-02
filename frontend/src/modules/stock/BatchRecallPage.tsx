import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, api } from '../../api';
import { can, useAuth } from '../auth';
import { DataTable, EmptyState, FormField, type Column } from '../../shell/components';

export interface BatchRecall {
  batch_id: number;
  batch_number: string;
  product_id: number;
  product_name: string | null;
  sku: string | null;
  variant_id: number | null;
  variant_sku: string | null;
  quantity_received: number;
  quantity_in_stock: number;
  locations: { location_id: number; location_name: string | null; quantity_in_stock: number }[];
  receipts: {
    location_id: number;
    location_name: string | null;
    reference_type: string;
    reference_id: number;
    quantity: number;
  }[];
  sold: {
    invoice_number: number;
    invoice_label: string;
    quantity_sold: number;
    quantity_returned: number;
    quantity_still_sold: number;
  }[];
}

type SoldRow = BatchRecall['sold'][number];
type LocationRow = BatchRecall['locations'][number];

function itemLabel(batch: BatchRecall): string {
  const name = batch.product_name ?? `Product ${batch.product_id}`;
  const sku = batch.variant_sku ?? batch.sku;
  return sku ? `${name} (${sku})` : name;
}

function BatchResult({ batch, linkInvoices }: { batch: BatchRecall; linkInvoices: boolean }) {
  const stillSold = batch.sold.reduce((sum, row) => sum + row.quantity_still_sold, 0);
  const locationColumns: Column<LocationRow>[] = [
    {
      header: 'Location',
      cell: (row) => row.location_name ?? `Location ${row.location_id}`,
    },
    { header: 'In stock', cell: (row) => row.quantity_in_stock },
  ];
  const soldColumns: Column<SoldRow>[] = [
    {
      header: 'Invoice',
      cell: (row) => {
        const label = row.invoice_label || `INV-${row.invoice_number}`;
        return linkInvoices ? (
          <Link to={`/sales/invoices/${row.invoice_number}`}>{label}</Link>
        ) : (
          label
        );
      },
    },
    { header: 'Sold', cell: (row) => row.quantity_sold },
    { header: 'Returned', cell: (row) => row.quantity_returned },
    { header: 'Still with customers', cell: (row) => row.quantity_still_sold },
  ];
  return (
    <section aria-label={`Batch ${batch.batch_number} of ${itemLabel(batch)}`}>
      <h2>
        {batch.batch_number}: {itemLabel(batch)}
      </h2>
      <p>
        Received {batch.quantity_received}, in stock {batch.quantity_in_stock}, sold and not
        returned {stillSold}.
      </p>
      <h3>Where it is in stock</h3>
      <DataTable
        caption={`Stock of batch ${batch.batch_number}`}
        columns={locationColumns}
        rows={batch.locations}
        rowKey={(row) => row.location_id}
        emptyMessage="No stock of this batch at any location."
      />
      <h3>Sold on invoices</h3>
      <DataTable
        caption={`Invoices for batch ${batch.batch_number}`}
        columns={soldColumns}
        rows={batch.sold}
        rowKey={(row) => row.invoice_number}
        emptyMessage="No units of this batch have been sold."
      />
    </section>
  );
}

/** Batch lookup for recalls (FR-2.5, FR2.5-IT-3): where a batch's units are and who bought them. */
export default function BatchRecallPage() {
  const { user } = useAuth();
  const [batchNumber, setBatchNumber] = useState('');
  const [results, setResults] = useState<BatchRecall[] | null>(null);
  const [error, setError] = useState('');
  const [searching, setSearching] = useState(false);

  async function search(event: FormEvent) {
    event.preventDefault();
    const number = batchNumber.trim();
    if (!number) {
      setError('Enter a batch number.');
      return;
    }
    setSearching(true);
    setError('');
    try {
      setResults(
        await api<BatchRecall[]>(
          `/sales/batches/recall?batch_number=${encodeURIComponent(number)}`,
        ),
      );
    } catch (cause) {
      setResults(null);
      if (cause instanceof ApiError && cause.status === 404) {
        setResults([]);
      } else {
        setError(cause instanceof ApiError ? cause.message : 'Could not look up the batch.');
      }
    } finally {
      setSearching(false);
    }
  }

  return (
    <div className="page">
      <h1>Batch recall</h1>
      <p>
        Look up a batch number to see how many units are still in stock, where, and which invoices
        the sold units went out on.
      </p>
      <form aria-label="Batch lookup" onSubmit={search} className="form-grid">
        <FormField label="Batch number" error={error}>
          {(props) => (
            <input
              {...props}
              value={batchNumber}
              onChange={(event) => setBatchNumber(event.target.value)}
              placeholder="e.g. BATCH-2026-08"
            />
          )}
        </FormField>
        <div>
          <button type="submit" disabled={searching}>
            {searching ? 'Searching…' : 'Look up'}
          </button>
        </div>
      </form>
      {results !== null &&
        (results.length === 0 ? (
          <EmptyState message="No batch with that number was found." />
        ) : (
          results.map((batch) => (
            <BatchResult
              key={batch.batch_id}
              batch={batch}
              linkInvoices={can(user, 'sales.record')}
            />
          ))
        ))}
    </div>
  );
}
