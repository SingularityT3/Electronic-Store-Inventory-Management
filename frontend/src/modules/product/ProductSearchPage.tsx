import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError } from '../../api';
import { can, useAuth } from '../auth';
import { DataTable, EmptyState, SearchBox } from '../../shell/components';
import { productApi, type Product } from './api';

const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' });
const PAGE_SIZE = 50;

export default function ProductSearchPage() {
  const { user } = useAuth();
  const [products, setProducts] = useState<Product[]>([]);
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let current = true;
    setLoading(true);
    setError('');
    productApi
      .list(page, PAGE_SIZE, query)
      .then((result) => {
        if (current) {
          setProducts(result.items);
          setTotal(result.total);
        }
      })
      .catch((e) => {
        if (current) setError(e instanceof ApiError ? e.message : 'Could not load products.');
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, [page, query]);

  function search(value: string) {
    setPage(1);
    setQuery(value);
  }

  return (
    <div className="page">
      <header className="page-header">
        <h1>Product search</h1>
      </header>
      <SearchBox onSearch={search} />
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {loading ? (
        <p>Loading products...</p>
      ) : products.length === 0 ? (
        <EmptyState message="No products found">
          <p>Try a shorter search, check the spelling, or search by SKU, brand or category.</p>
        </EmptyState>
      ) : (
        <DataTable
          caption="Product search results"
          rows={products}
          rowKey={(product) => product.id}
          emptyMessage="No products found"
          columns={[
            { header: 'SKU', cell: (product) => product.sku },
            {
              header: 'Name',
              cell: (product) =>
                can(user, 'products.manage') ? (
                  <Link to={`/products/${product.id}`}>{product.name}</Link>
                ) : (
                  product.name
                ),
            },
            { header: 'Brand', cell: (product) => product.brand },
            { header: 'Category', cell: (product) => product.category_path_label },
            { header: 'Price', cell: (product) => money.format(Number(product.price)) },
            { header: 'Stock', cell: (product) => product.stock },
            { header: 'Variants', cell: (product) => product.variant_count },
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
    </div>
  );
}
