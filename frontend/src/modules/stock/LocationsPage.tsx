import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { api, ApiError } from '../../api';
import { DataTable, FormField } from '../../shell/components';

interface ManagedLocation {
  id: number;
  name: string;
  type: 'store' | 'warehouse';
  address: string | null;
  is_active: boolean;
}

interface FormState {
  name: string;
  type: 'store' | 'warehouse';
  address: string;
  is_active: boolean;
}

const EMPTY_FORM: FormState = { name: '', type: 'store', address: '', is_active: true };
const TYPE_LABELS = { store: 'Store', warehouse: 'Warehouse' } as const;

/**
 * Stores and warehouses (FR-2.1, UC-07). A new location is usable at once in stock levels,
 * transfers, purchase orders and the point of sale. Deactivating hides it from those screens.
 */
export default function LocationsPage() {
  const [locations, setLocations] = useState<ManagedLocation[]>([]);
  const [editing, setEditing] = useState<ManagedLocation | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    setLocations(await api<ManagedLocation[]>('/stock/locations/all'));
  }, []);

  useEffect(() => {
    load()
      .catch((cause: unknown) =>
        setError(cause instanceof ApiError ? cause.message : 'Could not load locations.'),
      )
      .finally(() => setLoading(false));
  }, [load]);

  function startEdit(location: ManagedLocation | null) {
    setEditing(location);
    setForm(
      location
        ? {
            name: location.name,
            type: location.type,
            address: location.address ?? '',
            is_active: location.is_active,
          }
        : EMPTY_FORM,
    );
    setError('');
    setFieldErrors({});
    setNotice('');
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setFieldErrors({});
    setNotice('');
    if (!form.name.trim()) {
      setFieldErrors({ name: 'Location name is required.' });
      return;
    }
    const body = {
      name: form.name.trim(),
      type: form.type,
      address: form.address.trim() || null,
      is_active: form.is_active,
    };
    try {
      if (editing) {
        await api(`/stock/locations/${editing.id}`, { method: 'PATCH', body });
        setNotice(`${body.name} updated.`);
      } else {
        await api('/stock/locations', { method: 'POST', body });
        setNotice(`${body.name} added.`);
      }
      setEditing(null);
      setForm(EMPTY_FORM);
      await load();
    } catch (cause) {
      if (cause instanceof ApiError && Object.keys(cause.fields).length) {
        setFieldErrors(cause.fields);
      } else {
        setError(cause instanceof ApiError ? cause.message : 'Could not save the location.');
      }
    }
  }

  if (loading) return <p className="loading">Loading locations…</p>;

  return (
    <div className="page">
      <header className="page-header">
        <h1>Locations</h1>
        <button type="button" onClick={() => startEdit(null)}>
          New location
        </button>
      </header>
      {notice && <p role="status">{notice}</p>}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <form aria-label={editing ? 'Edit location' : 'Add location'} onSubmit={submit}>
        <h2>{editing ? `Edit ${editing.name}` : 'Add location'}</h2>
        <FormField label="Name" error={fieldErrors.name}>
          {(field) => (
            <input
              {...field}
              maxLength={100}
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
            />
          )}
        </FormField>
        <FormField label="Type" error={fieldErrors.type}>
          {(field) => (
            <select
              {...field}
              value={form.type}
              onChange={(event) =>
                setForm({ ...form, type: event.target.value as FormState['type'] })
              }
            >
              <option value="store">Store</option>
              <option value="warehouse">Warehouse</option>
            </select>
          )}
        </FormField>
        <FormField label="Address" error={fieldErrors.address}>
          {(field) => (
            <textarea
              {...field}
              value={form.address}
              onChange={(event) => setForm({ ...form, address: event.target.value })}
            />
          )}
        </FormField>
        {editing && (
          <FormField label="Active" hint="Inactive locations are hidden from stock and sales.">
            {(field) => (
              <input
                {...field}
                type="checkbox"
                checked={form.is_active}
                onChange={(event) => setForm({ ...form, is_active: event.target.checked })}
              />
            )}
          </FormField>
        )}
        <button type="submit">{editing ? 'Save changes' : 'Add location'}</button>{' '}
        {editing && (
          <button type="button" onClick={() => startEdit(null)}>
            Cancel
          </button>
        )}
      </form>
      <DataTable
        caption="Locations"
        columns={[
          { header: 'Name', cell: (row) => row.name },
          { header: 'Type', cell: (row) => TYPE_LABELS[row.type] },
          { header: 'Address', cell: (row) => row.address ?? '—' },
          { header: 'Status', cell: (row) => (row.is_active ? 'Active' : 'Inactive') },
          {
            header: 'Actions',
            cell: (row) => (
              <button type="button" aria-label={`Edit ${row.name}`} onClick={() => startEdit(row)}>
                Edit
              </button>
            ),
          },
        ]}
        rows={locations}
        rowKey={(row) => row.id}
        emptyMessage="No locations yet. Add a store or warehouse to start tracking stock."
      />
    </div>
  );
}
