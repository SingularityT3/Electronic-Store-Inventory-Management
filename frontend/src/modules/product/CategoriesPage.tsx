import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ApiError } from '../../api';
import {
  Breadcrumb,
  ConfirmDialog,
  DataTable,
  FormField,
  type Column,
} from '../../shell/components';
import { productApi, type Category, type CategoryProduct } from './api';

function fields(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError)) return {};
  if ('field' in error.fields && 'message' in error.fields) {
    return { [String(error.fields.field)]: String(error.fields.message) };
  }
  return error.fields;
}

export default function CategoriesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [categories, setCategories] = useState<Category[]>([]);
  const [selected, setSelected] = useState<Category | null>(null);
  const [products, setProducts] = useState<CategoryProduct[]>([]);
  const [name, setName] = useState('');
  const [parentId, setParentId] = useState<number | null>(null);
  const [editing, setEditing] = useState<Category | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const [confirm, setConfirm] = useState(false);

  const load = useCallback(async (categoryId?: number) => {
    const next = await productApi.categories();
    setCategories(next);
    if (categoryId !== undefined) {
      const category = next.find((item) => item.id === categoryId) ?? null;
      setSelected(category);
      if (category) setProducts((await productApi.categoryProducts(category.id)).items);
    }
  }, []);

  useEffect(() => {
    const requested = Number(searchParams.get('selected'));
    load(Number.isInteger(requested) && requested > 0 ? requested : undefined).catch(() =>
      setError('Could not load categories.'),
    );
  }, [load, searchParams]);

  const descendants = useMemo(() => {
    if (!editing) return new Set<number>();
    return new Set(
      categories
        .filter((category) => category.path.some((item) => item.id === editing.id))
        .map((category) => category.id),
    );
  }, [categories, editing]);

  function choose(category: Category) {
    setSelected(category);
    setSearchParams({ selected: String(category.id) });
    productApi
      .categoryProducts(category.id)
      .then((page) => setProducts(page.items))
      .catch(() => setError('Could not load category products.'));
  }

  function beginCreate(parent: Category | null = null) {
    setEditing(null);
    setName('');
    setParentId(parent?.id ?? null);
    setErrors({});
  }

  function beginEdit(category: Category) {
    setEditing(category);
    setName(category.name);
    setParentId(category.parent_id);
    setErrors({});
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError('');
    setErrors({});
    try {
      if (editing) await productApi.updateCategory(editing.id, { name, parent_id: parentId });
      else await productApi.createCategory({ name, parent_id: parentId });
      await load(editing?.id ?? selected?.id);
      beginCreate();
    } catch (e) {
      const detail = fields(e);
      if (Object.keys(detail).length) setErrors(detail);
      else setError(e instanceof ApiError ? e.message : 'Could not save category.');
    }
  }

  async function remove() {
    if (!selected) return;
    try {
      await productApi.removeCategory(selected.id);
      setConfirm(false);
      setSelected(null);
      setProducts([]);
      setSearchParams({});
      await load();
    } catch (e) {
      setConfirm(false);
      setError(e instanceof ApiError ? e.message : 'Could not delete category.');
    }
  }

  const columns: Column<CategoryProduct>[] = [
    { header: 'Name', cell: (row) => row.name },
    { header: 'SKU', cell: (row) => row.sku },
    { header: 'Brand', cell: (row) => row.brand },
    { header: 'Price', cell: (row) => row.price },
    { header: 'Category', cell: (row) => row.category_path_label },
  ];

  return (
    <div className="page">
      <header className="page-header">
        <h1>Categories</h1>
        <button type="button" onClick={() => beginCreate()}>
          Add top-level category
        </button>
      </header>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="category-layout">
        <section aria-label="Category tree">
          <h2>Category tree</h2>
          <ul>
            {categories.map((category) => (
              <li key={category.id} style={{ marginInlineStart: `${category.depth * 1.5}rem` }}>
                <button type="button" onClick={() => choose(category)}>
                  {category.name} ({category.product_count} ({category.total_product_count}))
                </button>{' '}
                <button type="button" onClick={() => beginCreate(category)}>
                  Add subcategory
                </button>{' '}
                <button type="button" onClick={() => beginEdit(category)}>
                  Rename / move
                </button>
              </li>
            ))}
          </ul>
        </section>
        <section>
          <h2>{editing ? 'Edit category' : 'Add category'}</h2>
          <form onSubmit={submit}>
            <FormField label="Category name" error={errors.name}>
              {(props) => (
                <input {...props} value={name} onChange={(event) => setName(event.target.value)} />
              )}
            </FormField>
            <FormField label="Parent category" error={errors.parent_id}>
              {(props) => (
                <select
                  {...props}
                  value={parentId ?? ''}
                  onChange={(event) =>
                    setParentId(event.target.value ? Number(event.target.value) : null)
                  }
                >
                  <option value="">No parent</option>
                  {categories
                    .filter((category) => !descendants.has(category.id))
                    .map((category) => (
                      <option key={category.id} value={category.id}>
                        {category.path_label}
                      </option>
                    ))}
                </select>
              )}
            </FormField>
            <button type="submit">{editing ? 'Save changes' : 'Add category'}</button>
          </form>
        </section>
      </div>
      {selected && (
        <section>
          <Breadcrumb
            items={selected.path.map((item) => ({
              label: item.name,
              to: `/categories?selected=${item.id}`,
            }))}
          />
          <h2>{selected.name} products</h2>
          <Link to={`/categories/${selected.id}/attributes`}>Manage attributes</Link>{' '}
          <button type="button" onClick={() => setConfirm(true)}>
            Delete category
          </button>
          <DataTable
            caption={`${selected.name} products`}
            columns={columns}
            rows={products}
            rowKey={(row) => row.id}
            emptyMessage="No products found"
          />
        </section>
      )}
      <ConfirmDialog
        open={confirm}
        title="Delete category"
        message={`Delete ${selected?.name ?? 'this category'}?`}
        confirmLabel="Delete"
        onConfirm={remove}
        onCancel={() => setConfirm(false)}
      />
    </div>
  );
}
