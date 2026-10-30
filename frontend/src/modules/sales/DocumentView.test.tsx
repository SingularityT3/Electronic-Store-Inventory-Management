import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DocumentView from './DocumentView';
import type { DocumentContent } from './api';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const invoice: DocumentContent = {
  kind: 'invoice',
  invoice_label: 'INV-0007',
  issued_at: '2026-10-30T10:00:00Z',
  store_name: 'ESIMS Electronics',
  store_gstin: 'GSTIN-123',
  location_name: 'Main Store',
  location_address: '1 Market Road',
  cashier_name: 'Ravi Kumar',
  customer_name: 'Jane Doe',
  gst_rate: '18.00',
  subtotal: '30000.00',
  discount_total: '0.00',
  tax_total: '5400.00',
  total: '35400.00',
  lines: [
    {
      product_name: 'Phone',
      sku: 'PHONE-1',
      quantity: 1,
      unit_price: '30000.00',
      tax: '5400.00',
      line_total: '35400.00',
    },
  ],
  payments: [{ method: 'cash', amount: '35400.00' }],
};

test('renders the invoice snapshot and prints the document', async () => {
  const print = vi.fn();
  vi.stubGlobal('fetch', vi.fn());
  vi.stubGlobal('print', print);
  render(<DocumentView document={invoice} pdfUrl="/sales/invoices/INV-0007/pdf" />);

  expect(screen.getByText('ESIMS Electronics')).toBeInTheDocument();
  expect(screen.getByText('INV-0007')).toBeInTheDocument();
  expect(screen.getByText(/Customer: Jane Doe/)).toBeInTheDocument();
  expect(document.querySelector('.document-totals')).toHaveTextContent('GST (18.00%)');
  await userEvent.click(screen.getByRole('button', { name: 'Print' }));
  expect(print).toHaveBeenCalledOnce();
});

test('PDF failures can be retried or dismissed to view the document', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: false,
    status: 500,
    json: async () => ({
      detail: 'Could not generate the PDF. You can try again or view the invoice on screen.',
    }),
  });
  vi.stubGlobal('fetch', fetchMock);
  render(<DocumentView document={invoice} pdfUrl="/sales/invoices/INV-0007/pdf" />);
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'Download PDF' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not generate the PDF.');
  await user.click(screen.getByRole('button', { name: 'Retry' }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  await user.click(screen.getByRole('button', { name: 'View on screen' }));
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  expect(screen.getByText('INV-0007')).toBeInTheDocument();
});

test('renders credit notes with the refund total and return status', () => {
  const creditNote: DocumentContent = {
    kind: 'credit_note',
    credit_note_number: 'CN-0003',
    created_at: '2026-10-30T10:00:00Z',
    store_name: 'ESIMS Electronics',
    location_name: 'Main Store',
    refund_total: '500.00',
    lines: [{ product_name: 'Mouse', sku: 'MOUSE-1', quantity: 1, refund_amount: '500.00' }],
  };
  render(
    <DocumentView
      document={creditNote}
      pdfUrl="/sales/returns/3/pdf"
      returnStatus="partially_returned"
    />,
  );
  expect(screen.getByText('CN-0003')).toBeInTheDocument();
  expect(screen.getByText('Partially Returned')).toBeInTheDocument();
  expect(screen.getByText('Refund total')).toBeInTheDocument();
});
