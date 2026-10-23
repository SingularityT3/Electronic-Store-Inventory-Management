import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError } from '../../api';
import { can, useAuth } from '../auth';
import { ConfirmDialog, DataTable, SearchBox } from '../../shell/components';
import { productApi, type Product, type ProductPage } from './api';

const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' });
const PAGE_SIZE = 50;

export default function ProductListPage() {
  const { user } = useAuth();
  const [products, setProducts] = useState<Product[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [deleting, setDeleting] = useState<Product | null>(null);
  const [query, setQuery] = useState('');

  const load = useCallback(
    (currentPage = page) => {
      setLoading(true);
      setError('');
      productApi
        .list(currentPage, PAGE_SIZE, query)
        .then((result: ProductPage) => {
          setProducts(result.items);
          setTotal(result.total);
        })
        .catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load products.'))
        .finally(() => setLoading(false));
    },
    [page, query],
  );

  useEffect(() => load(page), [load, page]);

  async function remove() {
    if (!deleting) return;
    try {
      await productApi.remove(deleting.id);
      setDeleting(null);
      setMessage('Product deleted successfully');
      load();
    } catch (e) {
      setDeleting(null);
      setError(e instanceof ApiError ? e.message : 'Could not delete product.');
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <h1>Products</h1>
        {can(user, 'products.manage') && (
          <Link to="/products/new">
            <button type="button">Add product</button>
          </Link>
        )}
      </header>
      <SearchBox
        value={query}
        onSearch={(value) => {
          setQuery(value);
          setPage(1);
        }}
      />
      {message && <p role="status">{message}</p>}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {loading ? (
        <p>Loading products...</p>
      ) : (
        <DataTable
          caption="Products"
          rows={products}
          rowKey={(product) => product.id}
          emptyMessage="No products found"
          columns={[
            { header: 'SKU', cell: (product) => product.sku },
            {
              header: 'Name',
              cell: (product) => <Link to={`/products/${product.id}`}>{product.name}</Link>,
            },
            { header: 'Category', cell: (product) => product.category_name },
            { header: 'Brand', cell: (product) => product.brand },
            { header: 'Price', cell: (product) => money.format(Number(product.price)) },
            ...(can(user, 'products.manage')
              ? [
                  {
                    header: 'Actions',
                    cell: (product: Product) => (
                      <>
                        <Link to={`/products/${product.id}/edit`}>Edit</Link>{' '}
                        <button type="button" onClick={() => setDeleting(product)}>
                          Delete
                        </button>
                      </>
                    ),
                  },
                ]
              : []),
          ]}
        />
      )}
      {!loading && total > PAGE_SIZE && (
        <div className="pager">
          <button type="button" disabled={page === 1} onClick={() => setPage(page - 1)}>
            Previous
          </button>
          <span>
            Page {page} of {Math.ceil(total / PAGE_SIZE)}
          </span>
          <button
            type="button"
            disabled={page >= Math.ceil(total / PAGE_SIZE)}
            onClick={() => setPage(page + 1)}
          >
            Next
          </button>
        </div>
      )}
      <ConfirmDialog
        open={deleting !== null}
        title="Delete product"
        message={deleting ? `Delete ${deleting.name}?` : ''}
        confirmLabel="Delete"
        onConfirm={remove}
        onCancel={() => setDeleting(null)}
      />
    </div>
  );
}
