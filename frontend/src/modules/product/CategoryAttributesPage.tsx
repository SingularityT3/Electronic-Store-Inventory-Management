import { useEffect, useState, type FormEvent } from 'react';
import { useParams } from 'react-router-dom';
import { ApiError } from '../../api';
import { ConfirmDialog, DataTable, FormField, type Column } from '../../shell/components';
import { productApi, type CategoryAttribute } from './api';

function fields(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError)) return {};
  if ('field' in error.fields && 'message' in error.fields) {
    return { [String(error.fields.field)]: String(error.fields.message) };
  }
  return error.fields;
}

export default function CategoryAttributesPage() {
  const { id } = useParams();
  const categoryId = Number(id);
  const [attributes, setAttributes] = useState<CategoryAttribute[]>([]);
  const [editing, setEditing] = useState<CategoryAttribute | null>(null);
  const [name, setName] = useState('');
  const [values, setValues] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const [confirm, setConfirm] = useState<CategoryAttribute | null>(null);

  useEffect(() => {
    productApi
      .attributes(categoryId)
      .then(setAttributes)
      .catch((reason) =>
        setError(reason instanceof ApiError ? reason.message : 'Could not load attributes.'),
      );
  }, [categoryId]);

  function begin(attribute: CategoryAttribute | null = null) {
    setEditing(attribute);
    setName(attribute?.name ?? '');
    setValues(attribute?.allowed_values?.join(', ') ?? '');
    setErrors({});
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError('');
    setErrors({});
    const body = {
      name,
      position: editing?.position ?? attributes.length,
      allowed_values: values.trim() ? values.split(',').map((value) => value.trim()) : null,
    };
    try {
      const saved = editing
        ? await productApi.updateAttribute(categoryId, editing.id, body)
        : await productApi.createAttribute(categoryId, body);
      setAttributes((current) =>
        editing
          ? current.map((item) => (item.id === saved.id ? saved : item))
          : [...current, saved],
      );
      begin();
    } catch (reason) {
      const detail = fields(reason);
      if (Object.keys(detail).length) setErrors(detail);
      else setError(reason instanceof ApiError ? reason.message : 'Could not save attribute.');
    }
  }

  async function remove() {
    if (!confirm) return;
    try {
      await productApi.removeAttribute(categoryId, confirm.id);
      setAttributes((current) => current.filter((item) => item.id !== confirm.id));
      setConfirm(null);
    } catch (reason) {
      setConfirm(null);
      setError(reason instanceof ApiError ? reason.message : 'Could not delete attribute.');
    }
  }

  const columns: Column<CategoryAttribute>[] = [
    { header: 'Name', cell: (row) => row.name },
    { header: 'Allowed values', cell: (row) => row.allowed_values?.join(', ') ?? 'Free text' },
    { header: 'Position', cell: (row) => row.position },
    {
      header: 'Actions',
      cell: (row) => (
        <>
          <button type="button" onClick={() => begin(row)}>
            Edit
          </button>{' '}
          <button type="button" onClick={() => setConfirm(row)}>
            Delete
          </button>
        </>
      ),
    },
  ];

  return (
    <div className="page">
      <header className="page-header">
        <h1>Category attributes</h1>
        <button type="button" onClick={() => begin()}>
          Add attribute
        </button>
      </header>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <DataTable
        caption="Category attributes"
        columns={columns}
        rows={attributes}
        rowKey={(row) => row.id}
        emptyMessage="No attributes yet"
      />
      <form onSubmit={submit}>
        <h2>{editing ? 'Edit attribute' : 'Add attribute'}</h2>
        <FormField label="Attribute name" error={errors.name}>
          {(props) => (
            <input {...props} value={name} onChange={(event) => setName(event.target.value)} />
          )}
        </FormField>
        <FormField
          label="Allowed values"
          error={errors.allowed_values}
          hint="Comma-separated; leave blank for free text."
        >
          {(props) => (
            <input {...props} value={values} onChange={(event) => setValues(event.target.value)} />
          )}
        </FormField>
        <button type="submit">{editing ? 'Save changes' : 'Add attribute'}</button>
        {editing && (
          <button type="button" onClick={() => begin()}>
            Cancel
          </button>
        )}
      </form>
      <ConfirmDialog
        open={confirm !== null}
        title="Delete attribute"
        message={`Delete ${confirm?.name ?? 'this attribute'}?`}
        confirmLabel="Delete"
        onConfirm={remove}
        onCancel={() => setConfirm(null)}
      />
    </div>
  );
}
