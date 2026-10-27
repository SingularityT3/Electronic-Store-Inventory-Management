import { useEffect, useMemo, useState } from 'react';
import { ApiError, api } from '../../api';
import { DataTable, FormField, type Column } from '../../shell/components';
import type { Product, ProductPage } from '../product/api';
import { purchasingApi, type Supplier, type SupplierPriceHistory } from './api';

function formatPrice(value: string): string {
  return Number(value).toFixed(2);
}

function loadProducts(): Promise<Product[]> {
  return api<ProductPage>('/product?page=1&page_size=50').then(async (first) => {
    const remaining = Math.max(0, Math.ceil(first.total / first.page_size) - 1);
    const pages = await Promise.all(
      Array.from({ length: remaining }, (_, index) =>
        api<ProductPage>(`/product?page=${index + 2}&page_size=50`),
      ),
    );
    return [...first.items, ...pages.flatMap((page) => page.items)];
  });
}

export default function SupplierPriceHistoryPage() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [history, setHistory] = useState<SupplierPriceHistory[]>([]);
  const [supplierId, setSupplierId] = useState('');
  const [productId, setProductId] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    Promise.all([purchasingApi.suppliers(), loadProducts()])
      .then(([supplierRows, productRows]) => {
        if (!active) return;
        setSuppliers(supplierRows);
        setProducts(productRows);
      })
      .catch((cause: unknown) => {
        if (active) {
          setError(cause instanceof ApiError ? cause.message : 'Could not load filter options.');
        }
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    const filters = {
      ...(supplierId ? { supplier_id: Number(supplierId) } : {}),
      ...(productId ? { product_id: Number(productId) } : {}),
    };
    purchasingApi
      .supplierPriceHistory(filters)
      .then((rows) => {
        if (active) {
          setHistory(rows);
          setError('');
        }
      })
      .catch((cause: unknown) => {
        if (active) {
          setError(cause instanceof ApiError ? cause.message : 'Could not load price history.');
        }
      });
    return () => {
      active = false;
    };
  }, [supplierId, productId]);

  const columns = useMemo<Column<SupplierPriceHistory>[]>(
    () => [
      { header: 'Supplier', cell: (entry) => entry.supplier_name },
      {
        header: 'Product / SKU',
        cell: (entry) => `${entry.product_name} (${entry.sku})`,
      },
      { header: 'Unit price', cell: (entry) => formatPrice(entry.unit_price) },
      {
        header: 'Receipt date',
        cell: (entry) => new Date(entry.recorded_at).toLocaleString(),
      },
    ],
    [],
  );

  if (loading) return <p className="loading">Loading supplier price history…</p>;

  return (
    <div className="page">
      <h1>Supplier price history</h1>
      <p>Receipt prices are retained as immutable historical entries.</p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="form-grid">
        <FormField label="Supplier">
          {(props) => (
            <select
              {...props}
              value={supplierId}
              onChange={(event) => setSupplierId(event.target.value)}
            >
              <option value="">All suppliers</option>
              {suppliers.map((supplier) => (
                <option key={supplier.id} value={supplier.id}>
                  {supplier.name}
                </option>
              ))}
            </select>
          )}
        </FormField>
        <FormField label="Product">
          {(props) => (
            <select
              {...props}
              value={productId}
              onChange={(event) => setProductId(event.target.value)}
            >
              <option value="">All products</option>
              {products.map((product) => (
                <option key={product.id} value={product.id}>
                  {product.name} ({product.sku})
                </option>
              ))}
            </select>
          )}
        </FormField>
      </div>
      <DataTable
        caption="Supplier price history"
        columns={columns}
        rows={history}
        rowKey={(entry) => entry.id}
        emptyMessage="No supplier price history matches these filters."
      />
    </div>
  );
}
