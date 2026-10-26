import { useEffect, useState, type FormEvent } from 'react';
import { productApi, type Category, type ProductQuery, type ProductSort } from './api';

type Filters = Omit<ProductQuery, 'q'>;

/** Sort choices as one list, so a cashier picks "Price: low to high" rather than two fields. */
const SORTS: { value: string; label: string; sort?: ProductSort; order?: 'asc' | 'desc' }[] = [
  { value: '', label: 'Best match / name' },
  { value: 'name-asc', label: 'Name: A to Z', sort: 'name', order: 'asc' },
  { value: 'name-desc', label: 'Name: Z to A', sort: 'name', order: 'desc' },
  { value: 'price-asc', label: 'Price: low to high', sort: 'price', order: 'asc' },
  { value: 'price-desc', label: 'Price: high to low', sort: 'price', order: 'desc' },
  { value: 'stock-asc', label: 'Stock: low to high', sort: 'stock', order: 'asc' },
  { value: 'stock-desc', label: 'Stock: high to low', sort: 'stock', order: 'desc' },
];

/**
 * Category (with subcategories), price range, stock level and sort for the product list
 * (FR-7.2). They combine with each other and with the search box.
 */
export default function ProductFilters({ onApply }: { onApply: (filters: Filters) => void }) {
  const [categories, setCategories] = useState<Category[]>([]);
  const [categoryId, setCategoryId] = useState('');
  const [minPrice, setMinPrice] = useState('');
  const [maxPrice, setMaxPrice] = useState('');
  const [stockStatus, setStockStatus] = useState('');
  const [sort, setSort] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let current = true;
    productApi
      .categories()
      .then((rows) => current && setCategories(rows))
      // Filtering by category is optional; the other filters still work without the list.
      .catch(() => current && setCategories([]));
    return () => {
      current = false;
    };
  }, []);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (minPrice && maxPrice && Number(minPrice) > Number(maxPrice)) {
      setError('Minimum price cannot be above the maximum price.');
      return;
    }
    setError('');
    const chosen = SORTS.find((option) => option.value === sort);
    onApply({
      category_id: categoryId ? Number(categoryId) : undefined,
      min_price: minPrice || undefined,
      max_price: maxPrice || undefined,
      stock_status: (stockStatus || undefined) as Filters['stock_status'],
      sort: chosen?.sort,
      order: chosen?.order,
    });
  }

  function clear() {
    setCategoryId('');
    setMinPrice('');
    setMaxPrice('');
    setStockStatus('');
    setSort('');
    setError('');
    onApply({});
  }

  return (
    <form className="audit-filters" aria-label="Filter products" onSubmit={submit}>
      <label>
        Category
        <select value={categoryId} onChange={(event) => setCategoryId(event.target.value)}>
          <option value="">All categories</option>
          {categories.map((category) => (
            <option key={category.id} value={category.id}>
              {category.path_label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Min price
        <input
          type="number"
          min="0"
          step="0.01"
          value={minPrice}
          onChange={(event) => setMinPrice(event.target.value)}
        />
      </label>
      <label>
        Max price
        <input
          type="number"
          min="0"
          step="0.01"
          value={maxPrice}
          onChange={(event) => setMaxPrice(event.target.value)}
        />
      </label>
      <label>
        Stock
        <select value={stockStatus} onChange={(event) => setStockStatus(event.target.value)}>
          <option value="">Any stock level</option>
          <option value="in_stock">In stock</option>
          <option value="low_stock">Low stock</option>
          <option value="out_of_stock">Out of stock</option>
        </select>
      </label>
      <label>
        Sort by
        <select value={sort} onChange={(event) => setSort(event.target.value)}>
          {SORTS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <button type="submit">Apply filters</button>
      <button type="button" onClick={clear}>
        Clear filters
      </button>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </form>
  );
}
