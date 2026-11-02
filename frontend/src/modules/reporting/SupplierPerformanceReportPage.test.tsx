import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import SupplierPerformanceReportPage from './SupplierPerformanceReportPage';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const supplierA = {
  supplier_id: 1,
  supplier_name: 'Alpha Electronics',
  purchase_order_count: 5,
  total_order_value: '2500.00',
  on_time_delivery_rate: '80.00',
  on_time_delivery_count: 4,
  eligible_delivery_count: 5,
  fulfilment_accuracy: '92.00',
  quantity_ordered: 50,
  quantity_accepted: 46,
  price_trends: [
    {
      product_id: 10,
      product_name: 'Phone',
      sku: 'PHONE-10',
      variant_id: null,
      price_points: [
        { recorded_at: '2026-10-10T10:00:00Z', unit_price: '100.00' },
        { recorded_at: '2026-10-20T10:00:00Z', unit_price: '120.00' },
      ],
      first_price: '100.00',
      latest_price: '120.00',
      variance: '20.00',
      variance_percent: '20.00',
    },
  ],
};

const supplierB = {
  ...supplierA,
  supplier_id: 2,
  supplier_name: 'Beta Devices',
  purchase_order_count: 3,
  total_order_value: '1200.00',
  on_time_delivery_rate: null,
  on_time_delivery_count: 0,
  eligible_delivery_count: 0,
  fulfilment_accuracy: null,
  quantity_ordered: 0,
  quantity_accepted: 0,
  price_trends: [],
};

function reply(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status < 400,
    status,
    json: async () => body,
  });
}

function renderPage() {
  render(
    <MemoryRouter>
      <SupplierPerformanceReportPage />
    </MemoryRouter>,
  );
}

test('renders supplier metrics and recorded product price changes side by side', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      reply({
        date_from: '2026-10-01',
        date_to: '2026-10-31',
        suppliers: [supplierA, supplierB],
      }),
    ),
  );
  renderPage();

  const comparison = await screen.findByRole('region', { name: 'Supplier comparison' });
  const alpha = within(comparison).getByRole('article', { name: 'Alpha Electronics' });
  const beta = within(comparison).getByRole('article', { name: 'Beta Devices' });
  expect(within(alpha).getByText('80.00% (4/5)')).toBeInTheDocument();
  expect(within(alpha).getByText('5')).toBeInTheDocument();
  expect(within(alpha).getByText('₹2,500.00')).toBeInTheDocument();
  expect(within(alpha).getByText('92.00% (46/50 units accepted)')).toBeInTheDocument();
  expect(within(alpha).getByText('Phone (PHONE-10)')).toBeInTheDocument();
  expect(within(alpha).getByText(/\+₹20\.00 \(20\.00%\)/)).toBeInTheDocument();
  expect(within(beta).getAllByText('—')).toHaveLength(2);
  expect(within(beta).getByText('No price history for this period.')).toBeInTheDocument();
});

test('date and supplier filters request a side-by-side comparison for the selected suppliers', async () => {
  const calls: string[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      calls.push(url);
      const selected = new URL(url, 'http://localhost').searchParams.getAll('supplier_ids');
      return reply({
        date_from: '2026-10-01',
        date_to: '2026-10-31',
        suppliers:
          selected.length > 0
            ? [supplierA, supplierB].filter((item) => selected.includes(String(item.supplier_id)))
            : [supplierA, supplierB],
      });
    }),
  );
  const user = userEvent.setup();
  renderPage();

  const supplierSelect = await screen.findByLabelText('Suppliers to compare');
  await user.selectOptions(supplierSelect, ['1', '2']);
  await waitFor(() => {
    expect(calls.some((url) => url.includes('supplier_ids=1&supplier_ids=2'))).toBe(true);
  });
  expect(screen.getByRole('article', { name: 'Alpha Electronics' })).toBeInTheDocument();
  expect(screen.getByRole('article', { name: 'Beta Devices' })).toBeInTheDocument();

  const from = screen.getByLabelText('From');
  await user.clear(from);
  await user.type(from, '2026-10-01');
  await waitFor(() =>
    expect(
      calls.some(
        (url) =>
          url.includes('date_from=2026-10-01') &&
          url.includes('supplier_ids=1') &&
          url.includes('supplier_ids=2'),
      ),
    ).toBe(true),
  );
});

test('shows loading, error and empty states', async () => {
  let resolveResponse: ((response: Awaited<ReturnType<typeof reply>>) => void) | undefined;
  vi.stubGlobal(
    'fetch',
    vi.fn(
      () =>
        new Promise((resolve) => {
          resolveResponse = resolve;
        }),
    ),
  );
  renderPage();
  expect(screen.getByText('Loading supplier performance report…')).toBeInTheDocument();
  resolveResponse?.(await reply({ date_from: '2026-10-01', date_to: '2026-10-31', suppliers: [] }));
  expect(
    await screen.findByText('No suppliers are available for this comparison.'),
  ).toBeInTheDocument();

  vi.stubGlobal(
    'fetch',
    vi.fn(() => reply({ detail: 'Report unavailable.' }, 500)),
  );
  cleanup();
  renderPage();
  expect(await screen.findByRole('alert')).toHaveTextContent('Report unavailable.');
});

test('exports the report shown on screen as CSV and PDF', async () => {
  const exportCalls: string[] = [];
  const createObjectURL = vi.fn(() => 'blob:export');
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  vi.stubGlobal('URL', { createObjectURL, revokeObjectURL: vi.fn() });
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      if (url.startsWith('/api/reporting/supplier-performance/export')) {
        exportCalls.push(url);
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers({
            'Content-Disposition':
              'attachment; filename="Supplier_Performance_Report_2026-10-31.csv"',
          }),
          blob: async () => new Blob(['x']),
        });
      }
      return reply({ date_from: '2026-10-01', date_to: '2026-10-31', suppliers: [supplierA] });
    }),
  );
  const user = userEvent.setup();
  renderPage();

  await screen.findByRole('region', { name: 'Supplier comparison' });
  await user.click(screen.getByRole('button', { name: 'Export CSV' }));
  await user.click(screen.getByRole('button', { name: 'Export PDF' }));

  await waitFor(() => expect(createObjectURL).toHaveBeenCalledTimes(2));
  expect(exportCalls).toEqual([
    '/api/reporting/supplier-performance/export?format=csv&date_from=2026-10-01&date_to=2026-10-31',
    '/api/reporting/supplier-performance/export?format=pdf&date_from=2026-10-01&date_to=2026-10-31',
  ]);
});
