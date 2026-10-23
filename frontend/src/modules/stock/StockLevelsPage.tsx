import { useEffect, useMemo, useState } from 'react';
import { api, ApiError } from '../../api';
import { DataTable } from '../../shell/components';

interface StockLevel {
  product_id: number;
  product_name: string;
  sku: string;
  category_id: number;
  category_name: string;
  variant_id: number | null;
  variant_sku: string | null;
  variant_attributes: Record<string, unknown> | null;
  location_id: number;
  location_name: string;
  quantity: number;
  total_quantity: number;
}

interface Location {
  id: number;
  name: string;
  type: string;
}

function itemLabel(row: StockLevel): string {
  return row.variant_sku
    ? `${row.product_name} (${row.variant_sku})`
    : `${row.product_name} (${row.sku})`;
}

export default function StockLevelsPage() {
  const [levels, setLevels] = useState<StockLevel[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);
  const [locationFilter, setLocationFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [productFilter, setProductFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let current = true;
    Promise.all([api<StockLevel[]>('/stock/levels'), api<Location[]>('/stock/locations')])
      .then(([stockLevels, stockLocations]) => {
        if (!current) return;
        setLevels(stockLevels);
        setLocations(stockLocations);
        setError('');
      })
      .catch((cause: unknown) => {
        if (!current) return;
        setError(cause instanceof ApiError ? cause.message : 'Could not load stock levels.');
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, []);

  const categories = useMemo(
    () =>
      [...new Map(levels.map((row) => [row.category_id, row.category_name])).entries()].sort(
        (a, b) => a[1].localeCompare(b[1]),
      ),
    [levels],
  );
  const products = useMemo(
    () =>
      [
        ...new Map(
          levels.map((row) => [row.product_id, `${row.product_name} (${row.sku})`]),
        ).entries(),
      ].sort((a, b) => a[1].localeCompare(b[1])),
    [levels],
  );
  const filtered = levels.filter(
    (row) =>
      (!locationFilter || row.location_id === Number(locationFilter)) &&
      (!categoryFilter || row.category_id === Number(categoryFilter)) &&
      (!productFilter || row.product_id === Number(productFilter)),
  );

  if (loading) return <p className="loading">Loading stock levels…</p>;

  return (
    <div className="page">
      <header className="page-header">
        <h1>Stock levels</h1>
      </header>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {!error && (
        <>
          <form className="audit-filters" aria-label="Filter stock levels">
            <label>
              Location
              <select
                aria-label="Location"
                value={locationFilter}
                onChange={(event) => setLocationFilter(event.target.value)}
              >
                <option value="">All locations</option>
                {locations.map((location) => (
                  <option key={location.id} value={location.id}>
                    {location.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Category
              <select
                aria-label="Category"
                value={categoryFilter}
                onChange={(event) => setCategoryFilter(event.target.value)}
              >
                <option value="">All categories</option>
                {categories.map(([id, name]) => (
                  <option key={id} value={id}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Product
              <select
                aria-label="Product"
                value={productFilter}
                onChange={(event) => setProductFilter(event.target.value)}
              >
                <option value="">All products</option>
                {products.map(([id, label]) => (
                  <option key={id} value={id}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          </form>
          <DataTable
            caption="Stock levels"
            columns={[
              { header: 'Product', cell: itemLabel },
              { header: 'Category', cell: (row) => row.category_name },
              { header: 'Location', cell: (row) => row.location_name },
              { header: 'Quantity', cell: (row) => row.quantity },
              { header: 'Combined total', cell: (row) => row.total_quantity },
            ]}
            rows={filtered}
            rowKey={(row) => `${row.product_id}-${row.variant_id ?? 'product'}-${row.location_id}`}
            emptyMessage="No stock levels match these filters."
          />
        </>
      )}
    </div>
  );
}
