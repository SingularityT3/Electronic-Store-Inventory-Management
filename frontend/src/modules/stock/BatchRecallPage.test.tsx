import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import App from '../../App';
import { AuthProvider, type Permission, type Role, type User } from '../auth';

const RECALL = [
  {
    batch_id: 7,
    batch_number: 'BATCH-2026-08',
    product_id: 3,
    product_name: 'Power Bank 10000mAh',
    sku: 'SKU-EL-2001',
    variant_id: null,
    variant_sku: null,
    quantity_received: 100,
    quantity_in_stock: 60,
    locations: [{ location_id: 1, location_name: 'Store-Chennai-01', quantity_in_stock: 60 }],
    receipts: [
      {
        location_id: 1,
        location_name: 'Store-Chennai-01',
        reference_type: 'po_receipt_line',
        reference_id: 4,
        quantity: 100,
      },
    ],
    sold: [
      {
        invoice_number: 5001,
        invoice_label: 'INV-5001',
        quantity_sold: 40,
        quantity_returned: 0,
        quantity_still_sold: 40,
      },
    ],
  },
];

const PERMISSIONS: Record<Role, Permission[]> = {
  admin: ['stock.view', 'sales.record'],
  manager: ['stock.view', 'sales.record'],
  staff: ['stock.view'],
  cashier: ['sales.record'],
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function signedInAs(role: Role) {
  const user: User = {
    id: 1,
    username: `${role}_user`,
    full_name: `Test ${role}`,
    role,
    location_id: role === 'staff' || role === 'cashier' ? 1 : null,
    permissions: PERMISSIONS[role],
  };
  const reply = (status: number, body?: unknown) =>
    Promise.resolve({ ok: status < 400, status, json: async () => body });
  const fetchMock = vi.fn((url: string) => {
    if (url === '/api/auth/me') return reply(200, user);
    if (url.startsWith('/api/notifications')) return reply(200, []);
    if (url === '/api/sales/batches/recall?batch_number=BATCH-2026-08') return reply(200, RECALL);
    if (url.startsWith('/api/sales/batches/recall')) {
      return reply(404, { detail: 'Batch not found.' });
    }
    return reply(404, { detail: 'Not found' });
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function renderAt(path: string) {
  render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}

// FR2.5-IT-3: a batch lookup shows the sold/in-stock split with invoice references.
test('looking up a batch number shows stock by location and the invoices it was sold on', async () => {
  signedInAs('manager');
  renderAt('/stock/batch-recall');

  await userEvent.type(await screen.findByLabelText('Batch number'), 'BATCH-2026-08');
  await userEvent.click(screen.getByRole('button', { name: 'Look up' }));

  const result = await screen.findByRole('region', {
    name: 'Batch BATCH-2026-08 of Power Bank 10000mAh (SKU-EL-2001)',
  });
  expect(result).toHaveTextContent('Received 100, in stock 60, sold and not returned 40.');
  const stock = within(result).getByRole('table', { name: 'Stock of batch BATCH-2026-08' });
  expect(stock).toHaveTextContent('Store-Chennai-01');
  expect(within(result).getByRole('link', { name: 'INV-5001' })).toHaveAttribute(
    'href',
    '/sales/invoices/5001',
  );
});

test('staff see invoice numbers without a link, and an unknown batch shows an empty state', async () => {
  signedInAs('staff');
  renderAt('/stock/batch-recall');

  await userEvent.type(await screen.findByLabelText('Batch number'), 'BATCH-2026-08');
  await userEvent.click(screen.getByRole('button', { name: 'Look up' }));
  expect(await screen.findByText('INV-5001')).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'INV-5001' })).not.toBeInTheDocument();

  const input = screen.getByLabelText('Batch number');
  await userEvent.clear(input);
  await userEvent.type(input, 'NOPE');
  await userEvent.click(screen.getByRole('button', { name: 'Look up' }));
  expect(await screen.findByText('No batch with that number was found.')).toBeInTheDocument();
});

test('cashiers are denied the batch recall screen', async () => {
  const fetchMock = signedInAs('cashier');
  renderAt('/stock/batch-recall');

  expect(await screen.findByRole('heading', { name: 'Access denied' })).toBeInTheDocument();
  expect(fetchMock.mock.calls.map(([url]) => url)).not.toContain(
    expect.stringContaining('/api/sales/batches'),
  );
});
