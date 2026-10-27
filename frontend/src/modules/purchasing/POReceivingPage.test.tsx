import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import App from '../../App';
import { AuthProvider, type User } from '../auth';
import type { PurchaseOrder } from './api';

const ORDER: PurchaseOrder = {
  id: 31,
  po_number: 'PO-20261027-1234ABCD',
  supplier_id: 5,
  supplier_name: 'Northwind Supply',
  location_id: 2,
  status: 'submitted',
  created_by: 1,
  notes: null,
  expected_delivery_date: '2026-11-12',
  submitted_at: '2026-10-27T10:00:00Z',
  created_at: '2026-10-27T09:00:00Z',
  lines: [
    {
      id: 41,
      product_id: 20,
      product_name: 'Phone',
      sku: 'PHONE-20',
      variant_id: null,
      tracking_mode: 'untracked',
      quantity_ordered: 2,
      quantity_received: 0,
      quantity_outstanding: 2,
      unit_price: '75.50',
      line_total: '151.00',
    },
  ],
  total: '151.00',
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function reply(status: number, body: unknown) {
  return Promise.resolve({ ok: status < 400, status, json: async () => body });
}

test('Staff can record a receipt through the PO receiving screen', async () => {
  const user: User = {
    id: 8,
    username: 'warehouse-staff',
    full_name: 'Warehouse Staff',
    role: 'staff',
    location_id: 2,
    permissions: ['purchase_orders.receive'],
  };
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      calls.push({ url, init });
      if (url === '/api/auth/me') return reply(200, user);
      if (url === '/api/purchasing/purchase-orders/receivable') {
        return reply(
          200,
          calls.filter((call) => call.init?.method === 'POST').length ? [] : [ORDER],
        );
      }
      if (url === `/api/purchasing/purchase-orders/${ORDER.id}/receive`) {
        return reply(200, {
          ...ORDER,
          status: 'partially_received',
          lines: [
            {
              ...ORDER.lines[0],
              quantity_received: 1,
              quantity_outstanding: 1,
            },
          ],
        });
      }
      return reply(404, { detail: 'Not found' });
    }),
  );
  render(
    <MemoryRouter
      initialEntries={['/purchase-orders/receive']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );

  const userAction = userEvent.setup();
  expect(await screen.findByRole('heading', { name: 'PO receiving' })).toBeInTheDocument();
  await userAction.click(await screen.findByRole('button', { name: ORDER.po_number }));
  await userAction.clear(screen.getByLabelText('Accepted PHONE-20'));
  await userAction.type(screen.getByLabelText('Accepted PHONE-20'), '1');
  await userAction.click(screen.getByRole('button', { name: 'Record receipt' }));

  const receiveCall = calls.find((call) => call.init?.method === 'POST');
  expect(receiveCall?.url).toBe(`/api/purchasing/purchase-orders/${ORDER.id}/receive`);
  expect(JSON.parse(String(receiveCall?.init?.body))).toEqual({
    notes: null,
    lines: [
      {
        po_line_id: ORDER.lines[0].id,
        quantity_accepted: 1,
        quantity_damaged: 0,
        quantity_short: 0,
        unit_price: '75.50',
        discrepancy_note: null,
      },
    ],
  });
  expect(await screen.findByText(`Receipt recorded for ${ORDER.po_number}.`)).toBeInTheDocument();
  expect(
    screen.getByRole('heading', { name: `Receive ${ORDER.po_number} · partially received` }),
  ).toBeInTheDocument();
});
