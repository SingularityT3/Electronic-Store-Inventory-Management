import { useEffect, useState, type FormEvent } from 'react';
import { api, ApiError } from '../../api';
import {
  ConfirmDialog,
  DataTable,
  EmptyState,
  FormField,
  type Column,
} from '../../shell/components';
import { AccessDenied } from '../../shell/components';
import { can, useAuth } from './AuthContext';

type Role = 'admin' | 'manager' | 'staff' | 'cashier';

interface ManagedUser {
  id: number;
  full_name: string;
  username: string;
  email: string | null;
  role: Role;
  location_id: number | null;
  is_active: boolean;
}

interface UserPage {
  users: ManagedUser[];
  total: number;
  limit: number;
  offset: number;
}

interface Location {
  id: number;
  name: string;
  type: string;
}

interface FormState {
  full_name: string;
  username: string;
  email: string;
  role: Role;
  location_id: string;
  is_active: boolean;
}

const EMPTY_FORM: FormState = {
  full_name: '',
  username: '',
  email: '',
  role: 'manager',
  location_id: '',
  is_active: true,
};

const ROLE_LABELS: Record<Role, string> = {
  admin: 'Admin',
  manager: 'Manager',
  staff: 'Staff',
  cashier: 'Cashier',
};

function formFor(user: ManagedUser): FormState {
  return {
    full_name: user.full_name,
    username: user.username,
    email: user.email ?? '',
    role: user.role,
    location_id: user.location_id === null ? '' : String(user.location_id),
    is_active: user.is_active,
  };
}

export default function UsersPage() {
  const { user: signedInUser } = useAuth();
  const allowed = can(signedInUser, 'users.manage');
  const [page, setPage] = useState<UserPage | null>(null);
  const [locations, setLocations] = useState<Location[]>([]);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [editing, setEditing] = useState<ManagedUser | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [confirming, setConfirming] = useState<ManagedUser | null>(null);
  const needsLocation = form.role === 'staff' || form.role === 'cashier';

  async function load() {
    const [users, availableLocations] = await Promise.all([
      api<UserPage>('/auth/users'),
      api<Location[]>('/stock/locations'),
    ]);
    setPage(users);
    setLocations(availableLocations);
  }

  useEffect(() => {
    if (!allowed) return;
    load().catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load users.'));
  }, [allowed]);

  function change<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
    setErrors((current) => ({ ...current, [key]: '' }));
  }

  function startCreate() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setErrors({});
    setError('');
    setSuccess('');
  }

  function startEdit(account: ManagedUser) {
    setEditing(account);
    setForm(formFor(account));
    setErrors({});
    setError('');
    setSuccess('');
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setErrors({});
    setError('');
    setSuccess('');
    const body = {
      full_name: form.full_name,
      username: form.username,
      email: form.email,
      role: form.role,
      location_id: form.location_id ? Number(form.location_id) : null,
      ...(editing ? { is_active: form.is_active } : {}),
    };
    try {
      if (editing) {
        await api(`/auth/users/${editing.id}`, { method: 'PATCH', body });
        setSuccess('User updated successfully.');
      } else {
        await api('/auth/users', { method: 'POST', body });
        setSuccess('User created. An invite link was emailed to the user.');
      }
      setEditing(null);
      setForm(EMPTY_FORM);
      await load();
    } catch (e) {
      if (e instanceof ApiError) {
        setErrors(e.fields);
        setError(Object.keys(e.fields).length ? '' : e.message);
      } else {
        setError('Could not save the user.');
      }
    }
  }

  async function setActive(account: ManagedUser) {
    try {
      await api(`/auth/users/${account.id}/${account.is_active ? 'deactivate' : 'reactivate'}`, {
        method: 'POST',
      });
      setConfirming(null);
      setSuccess(account.is_active ? 'User deactivated.' : 'User reactivated.');
      await load();
    } catch (e) {
      setConfirming(null);
      setError(e instanceof ApiError ? e.message : 'Could not change the user status.');
    }
  }

  const columns: Column<ManagedUser>[] = [
    { header: 'Name', cell: (account) => account.full_name },
    { header: 'Username', cell: (account) => account.username },
    { header: 'Email', cell: (account) => account.email ?? '—' },
    { header: 'Role', cell: (account) => ROLE_LABELS[account.role] },
    {
      header: 'Location',
      cell: (account) =>
        locations.find((location) => location.id === account.location_id)?.name ?? 'All locations',
    },
    { header: 'Status', cell: (account) => (account.is_active ? 'Active' : 'Disabled') },
    {
      header: 'Actions',
      cell: (account) => (
        <>
          <button type="button" onClick={() => startEdit(account)}>
            Edit
          </button>{' '}
          <button type="button" onClick={() => setConfirming(account)}>
            {account.is_active ? 'Deactivate' : 'Reactivate'}
          </button>
        </>
      ),
    },
  ];

  if (!allowed) return <AccessDenied what="user management" />;

  return (
    <div className="page">
      <header className="page-header">
        <h1>User management</h1>
        <button type="button" onClick={startCreate}>
          Add user
        </button>
      </header>
      {success && <p role="status">{success}</p>}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <form onSubmit={submit} aria-label={editing ? 'Edit user' : 'Add user'}>
        <FormField label="Name" error={errors.full_name}>
          {(control) => (
            <input
              {...control}
              value={form.full_name}
              onChange={(e) => change('full_name', e.target.value)}
              required
            />
          )}
        </FormField>
        <FormField label="Username" error={errors.username}>
          {(control) => (
            <input
              {...control}
              value={form.username}
              onChange={(e) => change('username', e.target.value)}
              required
            />
          )}
        </FormField>
        <FormField label="Email" error={errors.email}>
          {(control) => (
            <input
              {...control}
              type="email"
              value={form.email}
              onChange={(e) => change('email', e.target.value)}
              required
            />
          )}
        </FormField>
        <FormField label="Role" error={errors.role}>
          {(control) => (
            <select
              {...control}
              value={form.role}
              onChange={(e) => change('role', e.target.value as Role)}
            >
              {Object.entries(ROLE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          )}
        </FormField>
        {needsLocation && (
          <FormField label="Location" error={errors.location_id}>
            {(control) => (
              <select
                {...control}
                value={form.location_id}
                onChange={(e) => change('location_id', e.target.value)}
                required
              >
                <option value="">Choose a location</option>
                {locations.map((location) => (
                  <option key={location.id} value={location.id}>
                    {location.name}
                  </option>
                ))}
              </select>
            )}
          </FormField>
        )}
        {editing && (
          <FormField label="Active">
            {(control) => (
              <input
                {...control}
                type="checkbox"
                checked={form.is_active}
                onChange={(e) => change('is_active', e.target.checked)}
              />
            )}
          </FormField>
        )}
        <button type="submit">{editing ? 'Save changes' : 'Create user'}</button>
        {editing && (
          <button type="button" onClick={startCreate}>
            Cancel
          </button>
        )}
      </form>
      {page ? (
        <DataTable
          caption="Users"
          columns={columns}
          rows={page.users}
          rowKey={(account) => account.id}
          emptyMessage="No users found"
        />
      ) : (
        <EmptyState message="Loading users…" />
      )}
      <ConfirmDialog
        open={confirming !== null}
        title={confirming?.is_active ? 'Deactivate user?' : 'Reactivate user?'}
        message={
          confirming?.is_active
            ? 'This will end the user’s active sessions and prevent login.'
            : 'This will allow the user to sign in again.'
        }
        confirmLabel={confirming?.is_active ? 'Deactivate' : 'Reactivate'}
        onCancel={() => setConfirming(null)}
        onConfirm={() => confirming && setActive(confirming)}
      />
    </div>
  );
}
