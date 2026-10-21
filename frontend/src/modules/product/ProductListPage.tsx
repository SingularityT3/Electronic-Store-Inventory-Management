import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError } from '../../api';
import { ConfirmDialog, DataTable } from '../../shell/components';
import { productApi, type Product } from './api';

const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' });

export default function ProductListPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [deleting, setDeleting] = useState<Product | null>(null);

  function load() {
    productApi
      .list()
      .then((page) => setProducts(page.items))
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load products.'));
  }

  useEffect(load, []);

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
        <Link to="/products/new">
          <button type="button">Add product</button>
        </Link>
      </header>
      {message && <p role="status">{message}</p>}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
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
          {
            header: 'Actions',
            cell: (product) => (
              <>
                <Link to={`/products/${product.id}/edit`}>Edit</Link>{' '}
                <button type="button" onClick={() => setDeleting(product)}>
                  Delete
                </button>
              </>
            ),
          },
        ]}
      />
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
