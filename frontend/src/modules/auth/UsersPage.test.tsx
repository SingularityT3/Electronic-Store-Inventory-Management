import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import App from '../../App';
import { AuthProvider } from './AuthContext';

const ADMIN = {
  id: 1,
  username: 'admin',
  full_name: 'System Administrator',
  role: 'admin' as const,
  location_id: null,
  permissions: ['users.manage', 'stock.view'] as const,
};

const MANAGER = {
  ...ADMIN,
  role: 'manager' as const,
  permissions: ['stock.view'] as const,
};

function backend(role: 'admin' | 'manager' = 'admin', locked = false) {
  let users = [
    {
      id: 2,
      full_name: 'Manager Priya',
      username: 'priya',
      email: 'priya@example.com',
      role: 'manager',
      location_id: null,
      is_active: true,
      is_locked: locked,
    },
  ];
  const fetch = vi.fn((url: string, init?: RequestInit) => {
    const body = init?.body ? JSON.parse(init.body as string) : {};
    const signedIn = role === 'admin' ? ADMIN : MANAGER;
    if (url === '/api/auth/me') return Promise.resolve(reply(200, signedIn));
    if (url === '/api/stock/locations')
      return Promise.resolve(reply(200, [{ id: 1, name: 'Main Store', type: 'store' }]));
    if (url.startsWith('/api/auth/users?') && (!init || init.method === 'GET')) {
      return Promise.resolve(reply(200, { users, total: users.length, limit: 50, offset: 0 }));
    }
    if (url === '/api/auth/users' && init?.method === 'POST') {
      if (body.email.toLowerCase() === 'priya@example.com') {
        return Promise.resolve(reply(409, { detail: { email: 'This email is already in use.' } }));
      }
      users = [{ ...body, id: 3, is_active: true }, ...users];
      return Promise.resolve(reply(201, users[0]));
    }
    if (url === '/api/auth/users/2/unlock' && init?.method === 'POST') {
      users = users.map((user) => ({ ...user, is_locked: false }));
      return Promise.resolve(reply(200, users[0]));
    }
    if (url.includes('/deactivate')) {
      users = users.map((user) => ({ ...user, is_active: false }));
      return Promise.resolve(reply(200, users[0]));
    }
    return Promise.resolve(reply(403, { detail: 'You do not have permission to do this.' }));
  });
  vi.stubGlobal('fetch', fetch);
}

function reply(status: number, body?: unknown) {
  return { ok: status < 400, status, json: async () => body };
}

function renderUsers(role: 'admin' | 'manager' = 'admin') {
  render(
    <MemoryRouter
      initialEntries={['/users']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
  return role;
}

test('Admin can list users, see staff location, and receive inline duplicate errors', async () => {
  backend();
  renderUsers();
  expect(await screen.findByRole('table', { name: 'Users' })).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Add user' }));
  await userEvent.selectOptions(screen.getByLabelText('Role'), 'staff');
  expect(screen.getByLabelText('Location')).toBeInTheDocument();
  await userEvent.selectOptions(screen.getByLabelText('Location'), '1');
  await userEvent.type(screen.getByLabelText('Name'), 'Duplicate');
  await userEvent.type(screen.getByLabelText('Username'), 'duplicate');
  await userEvent.type(screen.getByLabelText('Email'), 'priya@example.com');
  await userEvent.click(screen.getByRole('button', { name: 'Create user' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('This email is already in use.');
});

test('Manager opening users sees Access denied', async () => {
  backend('manager');
  renderUsers('manager');
  await waitFor(() =>
    expect(screen.getByRole('heading', { name: 'Access denied' })).toBeInTheDocument(),
  );
});

test('Admin sees a locked account and unlocks it', async () => {
  backend('admin', true);
  renderUsers();
  const table = await screen.findByRole('table', { name: 'Users' });
  expect(table).toHaveTextContent('Locked');
  await userEvent.click(screen.getByRole('button', { name: 'Unlock priya' }));
  expect(await screen.findByRole('status')).toHaveTextContent('Manager Priya can sign in again.');
  await waitFor(() =>
    expect(screen.queryByRole('button', { name: 'Unlock priya' })).not.toBeInTheDocument(),
  );
});
