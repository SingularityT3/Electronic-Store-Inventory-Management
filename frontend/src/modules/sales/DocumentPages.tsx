import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api, ApiError } from '../../api';
import { useAuth } from '../auth';
import DataTable, { type Column } from '../../shell/components/DataTable';
import EmptyState from '../../shell/components/EmptyState';
import DocumentView from './DocumentView';
import {
  salesApi,
  type InvoiceDocument,
  type SalesHistory,
  type SalesHistoryItem,
  type ReturnCreditNote,
} from './api';

const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' });
const dateText = (value: string) => new Date(value).toLocaleString();

export function SalesHistoryPage() {
  const { user } = useAuth();
  const isManagerOrAdmin = user?.role === 'admin' || user?.role === 'manager';
  const [invoice, setInvoice] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [locationId, setLocationId] = useState('');
  const [locations, setLocations] = useState<{ id: number; name: string }[]>([]);
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<SalesHistory>({
    items: [],
    total: 0,
    page: 1,
    page_size: 25,
  });
  const [error, setError] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    if (isManagerOrAdmin)
      api<{ id: number; name: string }[]>('/stock/locations/all')
        .then(setLocations)
        .catch(() => setLocations([]));
  }, [isManagerOrAdmin]);
  useEffect(() => {
    const params = new URLSearchParams({ page: String(page), page_size: '25' });
    if (invoice.trim()) params.set('invoice', invoice.trim());
    if (dateFrom) params.set('date_from', dateFrom);
    if (dateTo) params.set('date_to', dateTo);
    if (isManagerOrAdmin && locationId) params.set('location_id', locationId);
    salesApi
      .history(params)
      .then((data) => {
        setResult(data);
        setError('');
      })
      .catch((cause: unknown) =>
        setError(cause instanceof Error ? cause.message : 'Could not load sales history.'),
      );
  }, [page, invoice, dateFrom, dateTo, locationId, isManagerOrAdmin]);

  const columns: Column<SalesHistoryItem>[] = [
    { header: 'Invoice', cell: (row) => row.invoice_label },
    { header: 'Date', cell: (row) => dateText(row.sold_at) },
    { header: 'Cashier', cell: (row) => row.cashier_name },
    { header: 'Location', cell: (row) => row.location_name },
    { header: 'Total', cell: (row) => money.format(Number(row.total)) },
    {
      header: 'Status',
      cell: (row) =>
        row.return_status === 'none' ? (
          'Not returned'
        ) : (
          <span
            className={`badge ${row.return_status === 'fully_returned' ? 'danger' : 'warning'}`}
          >
            {row.return_status === 'partially_returned' ? 'Partially Returned' : 'Fully Returned'}
          </span>
        ),
    },
    {
      header: 'Action',
      cell: (row) => (
        <button
          type="button"
          onClick={() => navigate(`/sales/invoices/${encodeURIComponent(row.invoice_label)}`)}
        >
          View
        </button>
      ),
    },
  ];

  return (
    <div className="page">
      <header className="page-header">
        <h1>Sales history</h1>
      </header>
      <form
        className="sales-history-filters"
        onSubmit={(event) => {
          event.preventDefault();
          setPage(1);
        }}
      >
        <label>
          Invoice number
          <input
            value={invoice}
            onChange={(event) => {
              setInvoice(event.target.value);
              setPage(1);
            }}
            placeholder="INV-0007"
          />
        </label>
        <label>
          Date from
          <input
            type="date"
            value={dateFrom}
            onChange={(event) => {
              setDateFrom(event.target.value);
              setPage(1);
            }}
          />
        </label>
        <label>
          Date to
          <input
            type="date"
            value={dateTo}
            onChange={(event) => {
              setDateTo(event.target.value);
              setPage(1);
            }}
          />
        </label>
        {isManagerOrAdmin && (
          <label>
            Location
            <select
              aria-label="Location"
              value={locationId}
              onChange={(event) => {
                setLocationId(event.target.value);
                setPage(1);
              }}
            >
              <option value="">All locations</option>
              {locations.map((location) => (
                <option key={location.id} value={location.id}>
                  {location.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <button type="submit">Search</button>
      </form>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {result.items.length ? (
        <DataTable
          caption="Sales history"
          columns={columns}
          rows={result.items}
          rowKey={(row) => row.sale_id}
          emptyMessage="No sales found"
        />
      ) : (
        <EmptyState message="No sales found">
          <p>Try another invoice number or date range.</p>
        </EmptyState>
      )}
      <nav className="pager" aria-label="Sales history pages">
        <button type="button" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>
          Previous
        </button>
        <span>
          Page {page} of {Math.max(1, Math.ceil(result.total / result.page_size))}
        </span>
        <button
          type="button"
          disabled={page * result.page_size >= result.total}
          onClick={() => setPage((value) => value + 1)}
        >
          Next
        </button>
      </nav>
    </div>
  );
}

export function InvoiceDocumentPage() {
  const { invoiceNumber = '' } = useParams();
  const [data, setData] = useState<InvoiceDocument | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    salesApi
      .getInvoiceDocument(invoiceNumber)
      .then(setData)
      .catch((cause: unknown) =>
        setError(cause instanceof ApiError ? cause.message : 'Invoice not found'),
      );
  }, [invoiceNumber]);
  if (error)
    return (
      <div className="page">
        <p role="alert">{error}</p>
      </div>
    );
  if (!data) return <p className="loading">Loading invoice…</p>;
  return (
    <div className="page">
      <DocumentView
        document={data.content}
        pdfUrl={`/sales/invoices/${encodeURIComponent(invoiceNumber)}/pdf`}
        returnStatus={data.return_status}
      />
      {data.credit_notes.length > 0 && (
        <section>
          <h2>Credit notes</h2>
          <ul>
            {data.credit_notes.map((note) => (
              <li key={note.return_id}>
                <Link to={`/sales/returns/${note.return_id}`}>{note.credit_note_number}</Link> ·{' '}
                {dateText(note.created_at)} · {money.format(Number(note.refund_total))}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

export function CreditNoteDocumentPage() {
  const { id = '' } = useParams();
  const [note, setNote] = useState<ReturnCreditNote | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    salesApi
      .getCreditNote(Number(id))
      .then(setNote)
      .catch((cause: unknown) =>
        setError(cause instanceof Error ? cause.message : 'Credit note not found'),
      );
  }, [id]);
  if (error)
    return (
      <div className="page">
        <p role="alert">{error}</p>
      </div>
    );
  if (!note) return <p className="loading">Loading credit note…</p>;
  const content = note.content ?? {
    kind: 'credit_note' as const,
    credit_note_number: note.credit_note_number,
    created_at: note.created_at,
    store_name: 'ESIMS Electronics',
    location_name: note.location_name,
    processor_name: note.processed_by_username,
    refund_total: note.refund_total,
    reason: note.reason,
    lines: note.lines.map((line) => ({
      id: line.id,
      product_name: line.product_name,
      sku: line.sku,
      quantity: line.quantity,
      refund_amount: line.refund_amount,
      line_total: line.refund_amount,
    })),
  };
  return (
    <div className="page">
      <DocumentView document={content} pdfUrl={`/sales/returns/${id}/pdf`} />
    </div>
  );
}
