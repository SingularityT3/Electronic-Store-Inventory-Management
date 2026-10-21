import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import App from '../../App';
import { AuthProvider, type User } from '../auth';
import type { AuditEntry } from './AuditLogPage';

const ADMIN: User = {
  id: 1,
  username: 'admin_asha',
  full_name: 'Asha Rao',
  role: 'admin',
  location_id: null,
  permissions: ['audit.view', 'users.manage'],
};

const MANAGER: User = {
  ...ADMIN,
  id: 2,
  username: 'manager_priya',
  role: 'manager',
  permissions: ['products.manage'],
};

function entry(fields: Partial<AuditEntry>): AuditEntry {
  return {
    id: 1,
    occurred_at: '2026-10-21T09:30:00Z',
    user_id: 2,
    username: 'manager_priya',
    module: 'product',
    action: 'product_price_updated',
    entity_type: 'product',
    entity_id: '1',
    details: null,
    before: null,
    after: null,
    ...fields,
  };
}

const ENTRIES = [
  entry({
    id: 2,
    before: { price: '28999.00' },
    after: { price: '26999.00' },
  }),
  entry({
    id: 1,
    username: 'staff_arun',
    module: 'stock',
    action: 'stock_adjusted',
    details: '<img src=x onerror="window.pwned=1">',
  }),
];

/** A fake backend that filters ENTRIES by username and records the requested URLs. */
function fakeBackend(user: User) {
  const urls: string[] = [];
  const reply = (status: number, body?: unknown) =>
    Promise.resolve({ ok: status < 400, status, json: async () => body });
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      urls.push(url);
      const parsed = new URL(url, 'http://esims.test');
      if (parsed.pathname === '/api/auth/me') return reply(200, user);
      if (parsed.pathname === '/api/audit/filters')
        return reply(200, {
          usernames: ['manager_priya', 'staff_arun'],
          actions: ['product_price_updated', 'stock_adjusted'],
          modules: ['product', 'stock'],
        });
      if (parsed.pathname === '/api/audit/entries') {
        const username = parsed.searchParams.get('username');
        const entries = ENTRIES.filter((e) => !username || e.username === username);
        return reply(200, { entries, total: entries.length, limit: 50, offset: 0 });
      }
      return reply(404, { detail: 'Not found' });
    }),
  );
  return urls;
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

test('Admin reaches the audit log from the dashboard', async () => {
  fakeBackend(ADMIN);
  renderAt('/');
  await userEvent.click(await screen.findByRole('link', { name: 'Audit log' }));
  expect(await screen.findByRole('heading', { name: 'Audit log' })).toBeInTheDocument();
});

// FR5.3-UT-2
test('entries show who, what and when, with old and new values', async () => {
  fakeBackend(ADMIN);
  renderAt('/audit');
  const rows = await screen.findAllByRole('row');
  const priceRow = within(rows[1]);
  expect(priceRow.getByText('manager_priya')).toBeInTheDocument();
  expect(priceRow.getByText('Product price updated')).toBeInTheDocument();
  expect(priceRow.getByText('price: 28999.00 → 26999.00')).toBeInTheDocument();
  expect(priceRow.getByRole('time')).toHaveAttribute('dateTime', '2026-10-21T09:30:00Z');
});

// FR5.3-UT-3
test('filtering by user shows only that user’s entries', async () => {
  const urls = fakeBackend(ADMIN);
  renderAt('/audit');
  await screen.findByText('staff_arun', { selector: 'td' });
  await userEvent.selectOptions(screen.getByLabelText('User'), 'manager_priya');
  await userEvent.click(screen.getByRole('button', { name: 'Apply' }));
  await screen.findByText('1–1 of 1');
  expect(screen.queryByText('staff_arun', { selector: 'td' })).not.toBeInTheDocument();
  expect(urls.at(-1)).toContain('username=manager_priya');
});

test('a date range is sent as local day boundaries', async () => {
  const urls = fakeBackend(ADMIN);
  renderAt('/audit');
  await screen.findAllByRole('row');
  await userEvent.type(screen.getByLabelText('From'), '2026-10-01');
  await userEvent.type(screen.getByLabelText('To'), '2026-10-21');
  await userEvent.click(screen.getByRole('button', { name: 'Apply' }));
  await vi.waitFor(() => expect(urls.at(-1)).toContain('since='));
  const params = new URL(urls.at(-1)!, 'http://esims.test').searchParams;
  expect(params.get('since')).toBe(new Date(2026, 9, 1).toISOString());
  expect(params.get('until')).toBe(new Date(2026, 9, 22).toISOString());
});

test('From after To cannot be applied', async () => {
  fakeBackend(ADMIN);
  renderAt('/audit');
  await screen.findAllByRole('row');
  await userEvent.type(screen.getByLabelText('From'), '2026-10-21');
  await userEvent.type(screen.getByLabelText('To'), '2026-10-01');
  expect(screen.getByRole('button', { name: 'Apply' })).toBeDisabled();
});

// UC-03 alternate flow 2a
test('no matching entries shows an empty state', async () => {
  fakeBackend(ADMIN);
  renderAt('/audit');
  await screen.findAllByRole('row');
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ entries: [], total: 0, limit: 50, offset: 0 }),
      }),
    ),
  );
  await userEvent.selectOptions(screen.getByLabelText('Action'), 'stock_adjusted');
  await userEvent.click(screen.getByRole('button', { name: 'Apply' }));
  expect(await screen.findByText('No audit entries match these filters.')).toBeInTheDocument();
});

// TC: a script in a logged reason is shown as text and does not run
test('logged text is shown as text, not markup', async () => {
  fakeBackend(ADMIN);
  renderAt('/audit');
  expect(await screen.findByText('<img src=x onerror="window.pwned=1">')).toBeInTheDocument();
  expect(document.querySelector('.audit-table img')).toBeNull();
});

// FR5.3-ST-2
test('a non-Admin is denied and the log is never requested', async () => {
  const urls = fakeBackend(MANAGER);
  renderAt('/audit');
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'You do not have permission to view the audit log.',
  );
  expect(urls.some((url) => url.startsWith('/api/audit'))).toBe(false);
});

test('the dashboard hides the audit log link from non-Admins', async () => {
  fakeBackend(MANAGER);
  renderAt('/');
  await screen.findByRole('heading', { name: 'Manager dashboard' });
  expect(screen.queryByRole('link', { name: 'Audit log' })).not.toBeInTheDocument();
});
