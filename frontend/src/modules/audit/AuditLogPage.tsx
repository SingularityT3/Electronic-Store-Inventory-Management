import { useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { api, ApiError } from '../../api';
import { can, useAuth } from '../auth';

export interface AuditEntry {
  id: number;
  occurred_at: string;
  user_id: number | null;
  username: string | null;
  module: string;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  details: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
}

interface AuditPage {
  entries: AuditEntry[];
  total: number;
  limit: number;
  offset: number;
}

interface FilterOptions {
  usernames: string[];
  actions: string[];
  modules: string[];
}

interface Filters {
  username: string;
  action: string;
  module: string;
  /** Local dates, YYYY-MM-DD; both ends inclusive. */
  from: string;
  to: string;
}

const NO_FILTERS: Filters = { username: '', action: '', module: '', from: '', to: '' };
const PAGE_SIZE = 50;

/** "login_failed" -> "Login failed". */
function actionLabel(action: string): string {
  const words = action.replace(/[_.]+/g, ' ').trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Start of a local date (YYYY-MM-DD), `days` later, as an ISO timestamp. */
function localDayStart(day: string, days = 0): string {
  const [y, m, d] = day.split('-').map(Number);
  return new Date(y, m - 1, d + days).toISOString();
}

function query(filters: Filters, offset: number): string {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
  if (filters.username) params.set('username', filters.username);
  if (filters.action) params.set('action', filters.action);
  if (filters.module) params.set('module', filters.module);
  if (filters.from) params.set('since', localDayStart(filters.from));
  if (filters.to) params.set('until', localDayStart(filters.to, 1));
  return params.toString();
}

function show(value: unknown): string {
  if (value === null || value === undefined) return '—';
  return typeof value === 'string' ? value : JSON.stringify(value);
}

/** Before/after values as "field: old → new" lines. */
function Changes({ entry }: { entry: AuditEntry }) {
  const before = entry.before ?? {};
  const after = entry.after ?? {};
  const fields = [...new Set([...Object.keys(before), ...Object.keys(after)])];
  if (fields.length === 0) return null;
  return (
    <ul className="audit-changes">
      {fields.map((field) => (
        <li key={field}>
          {field}:{' '}
          {entry.before && entry.after
            ? `${show(before[field])} → ${show(after[field])}`
            : show(entry.after ? after[field] : before[field])}
        </li>
      ))}
    </ul>
  );
}

/** Admin-only, read-only view of the audit log, filterable by user, date and action (UC-03). */
export default function AuditLogPage() {
  const { user } = useAuth();
  const allowed = can(user, 'audit.view');
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [draft, setDraft] = useState<Filters>(NO_FILTERS);
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<AuditPage | null>(null);
  const [options, setOptions] = useState<FilterOptions>({
    usernames: [],
    actions: [],
    modules: [],
  });
  const [error, setError] = useState('');

  useEffect(() => {
    if (!allowed) return;
    api<FilterOptions>('/audit/filters')
      .then(setOptions)
      .catch(() => {});
  }, [allowed]);

  useEffect(() => {
    if (!allowed) return;
    let current = true;
    setError('');
    api<AuditPage>(`/audit/entries?${query(filters, offset)}`)
      .then((result) => current && setPage(result))
      .catch((e) => {
        if (!current) return;
        setPage(null);
        setError(e instanceof ApiError ? e.message : 'Could not load the audit log.');
      });
    return () => {
      current = false;
    };
  }, [allowed, filters, offset]);

  if (!allowed) {
    return (
      <main className="page">
        <h1>Audit log</h1>
        <p role="alert" className="error">
          You do not have permission to view the audit log.
        </p>
        <Link to="/">Back to dashboard</Link>
      </main>
    );
  }

  const badRange = draft.from !== '' && draft.to !== '' && draft.from > draft.to;

  function apply(event: FormEvent) {
    event.preventDefault();
    if (badRange) return;
    setFilters(draft);
    setOffset(0);
  }

  function clear() {
    setDraft(NO_FILTERS);
    setFilters(NO_FILTERS);
    setOffset(0);
  }

  const field = (name: keyof Filters) => ({
    value: draft[name],
    onChange: (e: { target: { value: string } }) => setDraft({ ...draft, [name]: e.target.value }),
  });

  return (
    <main className="page">
      <header className="page-header">
        <h1>Audit log</h1>
        <Link to="/">Back to dashboard</Link>
      </header>

      <form className="audit-filters" onSubmit={apply} aria-label="Filter audit log">
        <label>
          User
          <select {...field('username')}>
            <option value="">All users</option>
            {options.usernames.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Action
          <select {...field('action')}>
            <option value="">All actions</option>
            {options.actions.map((action) => (
              <option key={action} value={action}>
                {actionLabel(action)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Module
          <select {...field('module')}>
            <option value="">All modules</option>
            {options.modules.map((module) => (
              <option key={module} value={module}>
                {actionLabel(module)}
              </option>
            ))}
          </select>
        </label>
        <label>
          From
          <input type="date" {...field('from')} max={draft.to || undefined} />
        </label>
        <label>
          To
          <input type="date" {...field('to')} min={draft.from || undefined} />
        </label>
        <button type="submit" disabled={badRange}>
          Apply
        </button>
        <button type="button" onClick={clear}>
          Clear
        </button>
        {badRange && <p className="error">The From date must not be after the To date.</p>}
      </form>

      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}

      {page && page.entries.length === 0 && (
        <p className="empty-state">No audit entries match these filters.</p>
      )}

      {page && page.entries.length > 0 && (
        <>
          <table className="audit-table">
            <thead>
              <tr>
                <th>When</th>
                <th>User</th>
                <th>Module</th>
                <th>Action</th>
                <th>Record</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {page.entries.map((entry) => (
                <tr key={entry.id}>
                  <td>
                    <time dateTime={entry.occurred_at}>
                      {new Date(entry.occurred_at).toLocaleString()}
                    </time>
                  </td>
                  <td>{entry.username ?? '—'}</td>
                  <td>{entry.module}</td>
                  <td title={entry.action}>{actionLabel(entry.action)}</td>
                  <td>
                    {entry.entity_type ? `${entry.entity_type} ${entry.entity_id ?? ''}` : ''}
                  </td>
                  <td>
                    {entry.details}
                    <Changes entry={entry} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <nav className="pager" aria-label="Pages">
            <span>
              {page.offset + 1}–{page.offset + page.entries.length} of {page.total}
            </span>
            <button
              disabled={page.offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              Previous
            </button>
            <button
              disabled={page.offset + page.entries.length >= page.total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Next
            </button>
          </nav>
        </>
      )}
    </main>
  );
}
