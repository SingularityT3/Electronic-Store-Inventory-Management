import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import App from '../../App';
import { AuthProvider, type User } from '../auth';
import ReturnsPage from './ReturnsPage';
import type { ReturnCreditNote, SaleLookup } from './api';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const CASHIER_USER: User = {
  id: 1,
  username: 'cashier_ram',
  full_name: 'Cashier Ram',
  role: 'cashier',
  location_id: 1,
  permissions: ['sales.record'],
};

const MANAGER_USER: User = {
  id: 2,
  username: 'manager_priya',
  full_name: 'Manager Priya',
  role: 'manager',
  location_id: 1,
  permissions: ['sales.record', 'returns.approve_late'],
};

const STAFF_USER: User = {
  id: 3,
  username: 'staff_anand',
  full_name: 'Staff Anand',
  role: 'staff',
  location_id: 1,
  permissions: ['products.view', 'stock.view'],
};

const SAMPLE_SALE: SaleLookup = {
  id: 10,
  location_id: 1,
  location_name: 'Main Store',
  cashier_id: 1,
  sold_at: '2026-10-25T10:00:00Z',
  subtotal: '101500.00',
  discount_total: '0.00',
  tax_total: '0.00',
  total: '101500.00',
  customer_name: 'Jane Doe',
  days_since_sale: 4,
  return_window_days: 30,
  requires_manager_approval: false,
  return_status: 'partially_returned',
  invoice: {
    invoice_number: 5002,
    invoice_label: 'INV-5002',
    issued_at: '2026-10-25T10:00:00Z',
    total: '101500.00',
  },
  lines: [
    {
      id: 101,
      product_id: 1,
      product_name: 'Wireless Mouse',
      sku: 'MOUSE-1',
      variant_id: null,
      variant_sku: null,
      variant_attributes: null,
      quantity: 3,
      unit_price: '500.00',
      discount_amount: '0.00',
      tax_amount: '0.00',
      line_total: '1500.00',
      serial_numbers: [],
      quantity_returned: 1,
      quantity_returnable: 2,
      returnable_serials: [],
      returnable_serial_ids: [],
    },
    {
      id: 102,
      product_id: 2,
      product_name: 'Pro Laptop',
      sku: 'LAPTOP-1',
      variant_id: null,
      variant_sku: null,
      variant_attributes: null,
      quantity: 2,
      unit_price: '50000.00',
      discount_amount: '0.00',
      tax_amount: '0.00',
      line_total: '100000.00',
      serial_numbers: ['SN-001', 'SN-002'],
      quantity_returned: 0,
      quantity_returnable: 2,
      returnable_serials: ['SN-001', 'SN-002'],
      returnable_serial_ids: [201, 202],
    },
  ],
};

const LATE_SALE: SaleLookup = {
  ...SAMPLE_SALE,
  days_since_sale: 35,
  requires_manager_approval: true,
};

const SAMPLE_CREDIT_NOTE: ReturnCreditNote = {
  return_id: 1,
  credit_note_number: 'CN-000001',
  sale_id: 10,
  invoice_number: 5002,
  created_at: '2026-10-29T10:00:00Z',
  location_id: 1,
  location_name: 'Main Store',
  processed_by_username: 'cashier_ram',
  approved_by_username: null,
  reason: 'Changed mind',
  refund_total: '500.00',
  non_sellable_quantity: 0,
  lines: [
    {
      id: 1,
      sale_line_id: 101,
      product_id: 1,
      product_name: 'Wireless Mouse',
      sku: 'MOUSE-1',
      variant_id: null,
      variant_sku: null,
      quantity: 1,
      condition: 'resaleable',
      restocked: true,
      refund_amount: '500.00',
      serial_numbers: [],
    },
  ],
};

function setupFetch(user: User, customHandler?: (url: string, init?: RequestInit) => unknown) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url.endsWith('/auth/me')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => user,
      });
    }
    if (customHandler) {
      const res = customHandler(url, init);
      if (res !== undefined) {
        return Promise.resolve(res);
      }
    }
    return Promise.resolve({
      ok: false,
      status: 404,
      json: async () => ({ detail: 'Not found' }),
    });
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function renderReturnsPage() {
  return render(
    <MemoryRouter initialEntries={['/returns']}>
      <AuthProvider>
        <ReturnsPage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

test('lookup success shows lines, returnable quantities and the Partially Returned status badge', async () => {
  setupFetch(CASHIER_USER, (url) => {
    if (url.includes('/sales/by-invoice/5002')) {
      return { ok: true, status: 200, json: async () => SAMPLE_SALE };
    }
  });

  renderReturnsPage();

  await userEvent.type(screen.getByLabelText('Invoice number'), '5002');
  await userEvent.click(screen.getByRole('button', { name: 'Look up' }));

  expect(await screen.findByText('Wireless Mouse')).toBeInTheDocument();
  expect(screen.getByText('Pro Laptop')).toBeInTheDocument();
  expect(screen.getByText('Partially Returned')).toBeInTheDocument();
  expect(screen.getByText('INV-5002')).toBeInTheDocument();
  expect(screen.getByText('Main Store')).toBeInTheDocument();
  expect(screen.getByText(/Days since sale:/i)).toBeInTheDocument();
  expect(screen.getByText('4')).toBeInTheDocument();
});

test('lookup failure shows "Invoice not found" inline and no lines table', async () => {
  setupFetch(CASHIER_USER, (url) => {
    if (url.includes('/sales/by-invoice/9999')) {
      return { ok: false, status: 404, json: async () => ({ detail: 'Invoice not found' }) };
    }
  });

  renderReturnsPage();

  await userEvent.type(screen.getByLabelText('Invoice number'), '9999');
  await userEvent.click(screen.getByRole('button', { name: 'Look up' }));

  expect(await screen.findByText('Invoice not found')).toBeInTheDocument();
  expect(screen.queryByRole('table', { name: 'Sale lines to return' })).not.toBeInTheDocument();
});

test('quantity cannot exceed returnable and clamps to maximum returnable', async () => {
  setupFetch(CASHIER_USER, (url) => {
    if (url.includes('/sales/by-invoice/5002')) {
      return { ok: true, status: 200, json: async () => SAMPLE_SALE };
    }
  });

  renderReturnsPage();

  await userEvent.type(screen.getByLabelText('Invoice number'), '5002');
  await userEvent.click(screen.getByRole('button', { name: 'Look up' }));

  const qtyInput = await screen.findByLabelText('Return quantity for Wireless Mouse');
  await userEvent.type(qtyInput, '5');
  // Maximum returnable is 2, so typing 5 clamps to 2
  expect(qtyInput).toHaveValue(2);
});

test('condition and reason preset interplay: choosing Defective - not sellable sets condition to Damaged', async () => {
  setupFetch(CASHIER_USER, (url) => {
    if (url.includes('/sales/by-invoice/5002')) {
      return { ok: true, status: 200, json: async () => SAMPLE_SALE };
    }
  });

  renderReturnsPage();

  await userEvent.type(screen.getByLabelText('Invoice number'), '5002');
  await userEvent.click(screen.getByRole('button', { name: 'Look up' }));

  const conditionSelect = (await screen.findByLabelText(
    'Condition for Wireless Mouse',
  )) as HTMLSelectElement;
  expect(conditionSelect.value).toBe('resaleable');

  const reasonSelect = screen.getByLabelText('Reason for return');
  await userEvent.selectOptions(reasonSelect, 'Defective - not sellable');

  expect(conditionSelect.value).toBe('damaged');
});

test('serial checkboxes control the return quantity for serial-tracked items', async () => {
  setupFetch(CASHIER_USER, (url) => {
    if (url.includes('/sales/by-invoice/5002')) {
      return { ok: true, status: 200, json: async () => SAMPLE_SALE };
    }
  });

  renderReturnsPage();

  await userEvent.type(screen.getByLabelText('Invoice number'), '5002');
  await userEvent.click(screen.getByRole('button', { name: 'Look up' }));

  expect(await screen.findByText('Selected: 0')).toBeInTheDocument();

  const sn1Checkbox = screen.getByLabelText('SN-001');
  const sn2Checkbox = screen.getByLabelText('SN-002');

  await userEvent.click(sn1Checkbox);
  expect(screen.getByText('Selected: 1')).toBeInTheDocument();

  await userEvent.click(sn2Checkbox);
  expect(screen.getByText('Selected: 2')).toBeInTheDocument();

  await userEvent.click(sn1Checkbox);
  expect(screen.getByText('Selected: 1')).toBeInTheDocument();
});

test('a late sale shows warning and approval dialog for a Cashier', async () => {
  setupFetch(CASHIER_USER, (url, init) => {
    if (url.includes('/sales/by-invoice/5002')) {
      return { ok: true, status: 200, json: async () => LATE_SALE };
    }
    if (url.includes('/sales/returns') && init?.method === 'POST') {
      const body = JSON.parse(String(init.body));
      if (body.manager_approval?.password === 'wrong') {
        return {
          ok: false,
          status: 403,
          json: async () => ({ detail: 'Manager approval failed.' }),
        };
      }
      return {
        ok: true,
        status: 201,
        json: async () => ({
          ...SAMPLE_CREDIT_NOTE,
          approved_by_username: 'manager_priya',
        }),
      };
    }
  });

  renderReturnsPage();

  await userEvent.type(screen.getByLabelText('Invoice number'), '5002');
  await userEvent.click(screen.getByRole('button', { name: 'Look up' }));

  expect(
    await screen.findByText('Older than 30 days: Manager approval required'),
  ).toBeInTheDocument();

  const qtyInput = screen.getByLabelText('Return quantity for Wireless Mouse');
  await userEvent.type(qtyInput, '1');

  await userEvent.click(screen.getByRole('button', { name: 'Process return' }));

  // Approval dialog opens
  expect(
    await screen.findByRole('alertdialog', { name: 'Manager approval required' }),
  ).toBeInTheDocument();
  const passwordInput = screen.getByLabelText('Manager password');
  expect(passwordInput).toHaveAttribute('type', 'password');

  // Submit wrong credentials
  await userEvent.type(screen.getByLabelText('Manager username'), 'manager_priya');
  await userEvent.type(passwordInput, 'wrong');
  await userEvent.click(screen.getByRole('button', { name: 'Approve' }));

  // Shows generic failure inside dialog and password cleared
  expect(await screen.findByText('Manager approval failed.')).toBeInTheDocument();
  expect(screen.getByLabelText('Manager password')).toHaveValue('');
  expect(screen.queryByText('wrong')).not.toBeInTheDocument();

  // Enter correct credentials
  await userEvent.type(screen.getByLabelText('Manager password'), 'correct_password');
  await userEvent.click(screen.getByRole('button', { name: 'Approve' }));

  // Return processed
  expect(await screen.findByText('Return processed')).toBeInTheDocument();
  expect(screen.getByText(/Approved by:/i)).toBeInTheDocument();
  expect(screen.getByText('manager_priya')).toBeInTheDocument();
});

test('a late sale processes directly without approval dialog when user is Manager', async () => {
  setupFetch(MANAGER_USER, (url, init) => {
    if (url.includes('/sales/by-invoice/5002')) {
      return { ok: true, status: 200, json: async () => LATE_SALE };
    }
    if (url.includes('/sales/returns') && init?.method === 'POST') {
      return {
        ok: true,
        status: 201,
        json: async () => ({
          ...SAMPLE_CREDIT_NOTE,
          approved_by_username: 'manager_priya',
        }),
      };
    }
  });

  renderReturnsPage();

  await userEvent.type(screen.getByLabelText('Invoice number'), '5002');
  await userEvent.click(screen.getByRole('button', { name: 'Look up' }));

  // Warning banner is NOT shown to managers/admins
  await waitFor(() => {
    expect(
      screen.queryByText('Older than 30 days: Manager approval required'),
    ).not.toBeInTheDocument();
  });

  const qtyInput = screen.getByLabelText('Return quantity for Wireless Mouse');
  await userEvent.type(qtyInput, '1');

  await userEvent.click(screen.getByRole('button', { name: 'Process return' }));

  // Dialog never opened; returns directly
  expect(await screen.findByText('Return processed')).toBeInTheDocument();
  expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
});

test('result panel shows credit note number, refund total and restock status', async () => {
  const damagedCreditNote: ReturnCreditNote = {
    ...SAMPLE_CREDIT_NOTE,
    refund_total: '500.00',
    non_sellable_quantity: 1,
    lines: [
      {
        id: 1,
        sale_line_id: 101,
        product_id: 1,
        product_name: 'Wireless Mouse',
        sku: 'MOUSE-1',
        variant_id: null,
        variant_sku: null,
        quantity: 1,
        condition: 'damaged',
        restocked: false,
        refund_amount: '500.00',
        serial_numbers: [],
      },
    ],
  };

  setupFetch(CASHIER_USER, (url, init) => {
    if (url.includes('/sales/by-invoice/5002')) {
      return { ok: true, status: 200, json: async () => SAMPLE_SALE };
    }
    if (url.includes('/sales/returns') && init?.method === 'POST') {
      return { ok: true, status: 201, json: async () => damagedCreditNote };
    }
  });

  renderReturnsPage();

  await userEvent.type(screen.getByLabelText('Invoice number'), '5002');
  await userEvent.click(screen.getByRole('button', { name: 'Look up' }));

  const qtyInput = await screen.findByLabelText('Return quantity for Wireless Mouse');
  await userEvent.type(qtyInput, '1');

  await userEvent.click(screen.getByRole('button', { name: 'Process return' }));

  expect(await screen.findByText('Return processed')).toBeInTheDocument();
  expect(screen.getAllByText('CN-000001')).toHaveLength(2);
  expect(screen.getByText('Not added to sellable stock (damaged)')).toBeInTheDocument();

  // Clicking New return resets the screen
  await userEvent.click(screen.getByRole('button', { name: 'New return' }));
  expect(screen.queryByText('Return processed')).not.toBeInTheDocument();
  expect(screen.getByLabelText('Invoice number')).toHaveValue('');
});

test('Staff user opening /returns sees Access denied', async () => {
  setupFetch(STAFF_USER);

  render(
    <MemoryRouter initialEntries={['/returns']}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );

  expect(await screen.findByRole('heading', { name: 'Access denied' })).toBeInTheDocument();
  expect(screen.getByText(/You do not have permission to view returns/i)).toBeInTheDocument();
});

test('Staff opening /sales/history sees Access denied', async () => {
  setupFetch(STAFF_USER);

  render(
    <MemoryRouter initialEntries={['/sales/history']}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );

  expect(await screen.findByRole('heading', { name: 'Access denied' })).toBeInTheDocument();
  expect(screen.getByText(/You do not have permission to view sales history/i)).toBeInTheDocument();
});
