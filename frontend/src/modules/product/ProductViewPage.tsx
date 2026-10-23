import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ApiError } from '../../api';
import {
  Breadcrumb,
  ConfirmDialog,
  DataTable,
  FormField,
  type Column,
} from '../../shell/components';
import { can, useAuth } from '../auth';
import {
  productApi,
  type CategoryAttribute,
  type Product,
  type ProductImage,
  type ProductVariant,
} from './api';

const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' });

export default function ProductViewPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [product, setProduct] = useState<Product | null>(null);
  const [images, setImages] = useState<ProductImage[]>([]);
  const [error, setError] = useState('');
  const [confirm, setConfirm] = useState(false);
  const [variants, setVariants] = useState<ProductVariant[]>([]);
  const [attributes, setAttributes] = useState<CategoryAttribute[]>([]);
  const [editing, setEditing] = useState<ProductVariant | null>(null);
  const [variantSku, setVariantSku] = useState('');
  const [variantPrice, setVariantPrice] = useState('');
  const [variantAttributes, setVariantAttributes] = useState<Record<string, string>>({});
  const [variantError, setVariantError] = useState('');
  const [variantErrors, setVariantErrors] = useState<Record<string, string>>({});
  const [variantConfirm, setVariantConfirm] = useState<ProductVariant | null>(null);

  useEffect(() => {
    productApi
      .get(Number(id))
      .then(setProduct)
      .catch(() => setError('Could not load product.'));
    productApi
      .images(Number(id))
      .then(setImages)
      .catch(() => setError('Could not load product images.'));
    productApi
      .variants(Number(id))
      .then(setVariants)
      .catch(() => setError('Could not load product variants.'));
  }, [id]);

  useEffect(() => {
    if (product) {
      productApi
        .attributes(product.category_id)
        .then(setAttributes)
        .catch(() => setError('Could not load category attributes.'));
    }
  }, [product]);

  function beginVariant(variant: ProductVariant | null = null) {
    setEditing(variant);
    setVariantSku(variant?.sku ?? '');
    setVariantPrice(variant?.price ?? '');
    setVariantAttributes(variant?.attributes ?? {});
    setVariantError('');
    setVariantErrors({});
  }

  function fieldErrors(error: unknown): Record<string, string> {
    if (!(error instanceof ApiError)) return {};
    if ('field' in error.fields && 'message' in error.fields) {
      return { [String(error.fields.field)]: String(error.fields.message) };
    }
    return error.fields;
  }

  async function saveVariant(event: FormEvent) {
    event.preventDefault();
    setVariantError('');
    setVariantErrors({});
    try {
      const saved = editing
        ? await productApi.updateVariant(Number(id), editing.id, {
            sku: variantSku,
            attributes: variantAttributes,
            price: variantPrice.trim() || null,
          })
        : await productApi.createVariant(Number(id), {
            sku: variantSku,
            attributes: variantAttributes,
            price: variantPrice.trim() || null,
          });
      setVariants((current) =>
        editing
          ? current.map((item) => (item.id === saved.id ? saved : item))
          : [...current, saved],
      );
      beginVariant();
    } catch (error) {
      const fields = fieldErrors(error);
      if (Object.keys(fields).length) setVariantErrors(fields);
      else setVariantError(error instanceof ApiError ? error.message : 'Could not save variant.');
    }
  }

  async function removeVariant() {
    if (!variantConfirm) return;
    try {
      await productApi.removeVariant(Number(id), variantConfirm.id);
      setVariants((current) => current.filter((item) => item.id !== variantConfirm.id));
      setVariantConfirm(null);
    } catch (error) {
      setVariantConfirm(null);
      setVariantError(error instanceof ApiError ? error.message : 'Could not delete variant.');
    }
  }

  async function remove() {
    try {
      await productApi.remove(Number(id));
      navigate('/products');
    } catch (e) {
      setConfirm(false);
      setError(e instanceof ApiError ? e.message : 'Could not delete product.');
    }
  }

  if (!product)
    return (
      <div className="page">
        {error ? (
          <p role="alert" className="error">
            {error}
          </p>
        ) : (
          'Loading...'
        )}
      </div>
    );
  return (
    <div className="page">
      <header className="page-header">
        <h1>{product.name}</h1>
        {can(user, 'products.manage') && (
          <span>
            <Link to={`/products/${product.id}/edit`}>Edit</Link>{' '}
            <button type="button" onClick={() => setConfirm(true)}>
              Delete
            </button>
          </span>
        )}
      </header>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <dl>
        <dt>SKU</dt>
        <dd>{product.sku}</dd>
        <dt>Category</dt>
        <dd>
          <Breadcrumb
            items={product.category_path.map((item) => ({
              label: item.name,
              to: `/categories?selected=${item.id}`,
            }))}
          />
        </dd>
        <dt>Brand</dt>
        <dd>{product.brand}</dd>
        <dt>Price</dt>
        <dd>{money.format(Number(product.price))}</dd>
        <dt>Description</dt>
        <dd>{product.description || '—'}</dd>
      </dl>
      <div className="product-images">
        {images.map((image) => (
          <img key={image.id} src={`/api${image.url}`} alt={`${product.name} product`} />
        ))}
      </div>
      <section aria-labelledby="variants-heading">
        <header className="page-header">
          <h2 id="variants-heading">Variants</h2>
          {can(user, 'products.manage') && (
            <button type="button" onClick={() => beginVariant()}>
              Add variant
            </button>
          )}
        </header>
        {variantError && (
          <p role="alert" className="error">
            {variantError}
          </p>
        )}
        <DataTable
          caption="Product variants"
          columns={
            [
              { header: 'SKU', cell: (row) => row.sku },
              { header: 'Attributes', cell: (row) => row.display_attributes.join(' / ') },
              {
                header: 'Price',
                cell: (row) =>
                  row.price === null ? 'uses base price' : money.format(Number(row.price)),
              },
              { header: 'Stock', cell: (row) => row.stock },
              ...(can(user, 'products.manage')
                ? [
                    {
                      header: 'Actions',
                      cell: (row: ProductVariant) => (
                        <>
                          <button type="button" onClick={() => beginVariant(row)}>
                            Edit
                          </button>{' '}
                          <button type="button" onClick={() => setVariantConfirm(row)}>
                            Delete
                          </button>
                        </>
                      ),
                    },
                  ]
                : []),
            ] as Column<ProductVariant>[]
          }
          rows={variants}
          rowKey={(row) => row.id}
          emptyMessage="No variants yet"
        />
        {can(user, 'products.manage') && (
          <form onSubmit={saveVariant}>
            <h3>{editing ? 'Edit variant' : 'Add variant'}</h3>
            <FormField label="SKU" error={variantErrors.sku}>
              {(props) => (
                <input
                  {...props}
                  value={variantSku}
                  onChange={(event) => setVariantSku(event.target.value)}
                />
              )}
            </FormField>
            {attributes.map((attribute) => (
              <FormField key={attribute.id} label={attribute.name} error={variantErrors.attributes}>
                {(props) =>
                  attribute.allowed_values ? (
                    <select
                      {...props}
                      value={variantAttributes[attribute.name] ?? ''}
                      onChange={(event) =>
                        setVariantAttributes((current) => ({
                          ...current,
                          [attribute.name]: event.target.value,
                        }))
                      }
                    >
                      <option value="">Choose {attribute.name}</option>
                      {attribute.allowed_values.map((value) => (
                        <option key={value}>{value}</option>
                      ))}
                    </select>
                  ) : (
                    <input
                      {...props}
                      value={variantAttributes[attribute.name] ?? ''}
                      onChange={(event) =>
                        setVariantAttributes((current) => ({
                          ...current,
                          [attribute.name]: event.target.value,
                        }))
                      }
                    />
                  )
                }
              </FormField>
            ))}
            <FormField
              label="Variant price"
              error={variantErrors.price}
              hint="Leave blank to use the base price."
            >
              {(props) => (
                <input
                  {...props}
                  type="number"
                  min="0"
                  step="0.01"
                  value={variantPrice}
                  onChange={(event) => setVariantPrice(event.target.value)}
                />
              )}
            </FormField>
            <button type="submit">{editing ? 'Save changes' : 'Add variant'}</button>
            {editing && (
              <button type="button" onClick={() => beginVariant()}>
                Cancel
              </button>
            )}
          </form>
        )}
      </section>
      <ConfirmDialog
        open={variantConfirm !== null}
        title="Delete variant"
        message={`Delete ${variantConfirm?.sku ?? 'this variant'}?`}
        confirmLabel="Delete"
        onConfirm={removeVariant}
        onCancel={() => setVariantConfirm(null)}
      />
      <ConfirmDialog
        open={confirm}
        title="Delete product"
        message={`Delete ${product.name}?`}
        confirmLabel="Delete"
        onConfirm={remove}
        onCancel={() => setConfirm(false)}
      />
    </div>
  );
}
