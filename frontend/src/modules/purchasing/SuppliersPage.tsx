import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { ApiError, api } from '../../api';
import { DataTable, FormField, type Column } from '../../shell/components';
import type { Product, ProductPage, ProductVariant } from '../product/api';
import { purchasingApi, type Supplier, type SupplierProduct } from './api';

interface CatalogChoice {
  value: string;
  product_id: number;
  variant_id: number | null;
  label: string;
}

function productPages(): Promise<Product[]> {
  return api<ProductPage>('/product?page=1&page_size=50').then(async (first) => {
    const pages = await Promise.all(
      Array.from({ length: Math.ceil(first.total / first.page_size) - 1 }, (_, index) =>
        api<ProductPage>(`/product?page=${index + 2}&page_size=50`),
      ),
    );
    return [...first.items, ...pages.flatMap((page) => page.items)];
  });
}

export default function SuppliersPage() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [selected, setSelected] = useState<Supplier | null>(null);
  const [catalog, setCatalog] = useState<SupplierProduct[]>([]);
  const [editingEntry, setEditingEntry] = useState<SupplierProduct | null>(null);
  const [name, setName] = useState('');
  const [contactName, setContactName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [address, setAddress] = useState('');
  const [productChoice, setProductChoice] = useState('');
  const [variants, setVariants] = useState<ProductVariant[]>([]);
  const [supplierSku, setSupplierSku] = useState('');
  const [supplierPrice, setSupplierPrice] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [status, setStatus] = useState('');

  const loadSuppliers = useCallback(async (selectedId?: number) => {
    const rows = await purchasingApi.suppliers();
    setSuppliers(rows);
    const next = rows.find((row) => row.id === selectedId) ?? null;
    setSelected(next);
    if (next) {
      setName(next.name);
      setContactName(next.contact_name ?? '');
      setEmail(next.email ?? '');
      setPhone(next.phone ?? '');
      setAddress(next.address ?? '');
      setCatalog(await purchasingApi.supplierProducts(next.id));
    } else {
      setCatalog([]);
    }
  }, []);

  useEffect(() => {
    let current = true;
    Promise.all([purchasingApi.suppliers(), productPages()])
      .then(([suppliersResult, productsResult]) => {
        if (!current) return;
        setSuppliers(suppliersResult);
        setProducts(productsResult);
      })
      .catch((cause: unknown) => {
        if (current) {
          setError(cause instanceof ApiError ? cause.message : 'Could not load suppliers.');
        }
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, []);

  useEffect(() => {
    const productId = Number(productChoice.split(':')[0]);
    if (!productId) {
      setVariants([]);
      return;
    }
    let current = true;
    api<ProductVariant[]>(`/product/${productId}/variants`)
      .then((rows) => {
        if (current) setVariants(rows);
      })
      .catch((cause: unknown) => {
        if (current) {
          setError(cause instanceof ApiError ? cause.message : 'Could not load product variants.');
        }
      });
    return () => {
      current = false;
    };
  }, [productChoice]);

  const choices: CatalogChoice[] = products.flatMap((product) => [
    {
      value: `${product.id}:`,
      product_id: product.id,
      variant_id: null,
      label: `${product.name} (${product.sku})`,
    },
    ...variants
      .filter((variant) => variant.product_id === product.id)
      .map((variant) => ({
        value: `${product.id}:${variant.id}`,
        product_id: product.id,
        variant_id: variant.id,
        label: `${product.name} (${variant.sku})`,
      })),
  ]);

  function chooseSupplier(supplier: Supplier) {
    setError('');
    setStatus('');
    setFieldErrors({});
    setEditingEntry(null);
    loadSuppliers(supplier.id).catch((cause: unknown) =>
      setError(cause instanceof ApiError ? cause.message : 'Could not load supplier details.'),
    );
  }

  function clearSupplierForm() {
    setSelected(null);
    setName('');
    setContactName('');
    setEmail('');
    setPhone('');
    setAddress('');
    setCatalog([]);
    setEditingEntry(null);
    setError('');
    setFieldErrors({});
    setStatus('');
  }

  async function saveSupplier(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setFieldErrors({});
    setStatus('');
    const body = {
      name,
      contact_name: contactName || null,
      email: email || null,
      phone: phone || null,
      address: address || null,
    };
    try {
      const saved = selected
        ? await purchasingApi.updateSupplier(selected.id, body)
        : await purchasingApi.createSupplier(body);
      await loadSuppliers(saved.id);
      setStatus(selected ? 'Supplier updated.' : 'Supplier created.');
    } catch (cause) {
      if (cause instanceof ApiError) {
        setError(cause.message);
        setFieldErrors(cause.fields);
      } else {
        setError('Could not save supplier.');
      }
    }
  }

  async function deactivateSupplier() {
    if (!selected) return;
    setError('');
    setStatus('');
    try {
      await purchasingApi.deactivateSupplier(selected.id);
      await loadSuppliers();
      clearSupplierForm();
      setStatus('Supplier deactivated.');
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not deactivate supplier.');
    }
  }

  async function saveCatalogItem(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    setError('');
    setFieldErrors({});
    setStatus('');
    try {
      if (editingEntry) {
        await purchasingApi.updateSupplierProduct(selected.id, editingEntry.id, {
          supplier_sku: supplierSku || null,
          supplier_price: supplierPrice,
        });
      } else {
        const choice = choices.find((item) => item.value === productChoice);
        if (!choice) {
          setError('Choose a product or variant.');
          return;
        }
        await purchasingApi.addSupplierProduct(selected.id, {
          product_id: choice.product_id,
          variant_id: choice.variant_id,
          supplier_sku: supplierSku || null,
          supplier_price: supplierPrice,
        });
      }
      setCatalog(await purchasingApi.supplierProducts(selected.id));
      setEditingEntry(null);
      setProductChoice('');
      setSupplierSku('');
      setSupplierPrice('');
      setStatus(editingEntry ? 'Catalog item updated.' : 'Catalog item added.');
    } catch (cause) {
      if (cause instanceof ApiError) {
        setError(cause.message);
        setFieldErrors(cause.fields);
      } else {
        setError('Could not save supplier catalog item.');
      }
    }
  }

  async function removeCatalogItem(entry: SupplierProduct) {
    if (!selected) return;
    try {
      await purchasingApi.removeSupplierProduct(selected.id, entry.id);
      setCatalog(await purchasingApi.supplierProducts(selected.id));
      setStatus('Catalog item removed.');
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not remove catalog item.');
    }
  }

  const columns: Column<Supplier>[] = [
    {
      header: 'Supplier',
      cell: (row) => (
        <button type="button" onClick={() => chooseSupplier(row)}>
          {row.name}
        </button>
      ),
    },
    { header: 'Email', cell: (row) => row.email ?? '—' },
    { header: 'Status', cell: (row) => (row.is_active ? 'Active' : 'Inactive') },
  ];

  if (loading) return <p className="loading">Loading suppliers…</p>;

  return (
    <div className="page">
      <header className="page-header">
        <h1>Suppliers</h1>
        <button type="button" onClick={clearSupplierForm}>
          Add supplier
        </button>
      </header>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {status && <p role="status">{status}</p>}
      <DataTable
        caption="Suppliers"
        columns={columns}
        rows={suppliers}
        rowKey={(row) => row.id}
        emptyMessage="No suppliers found."
      />
      <section>
        <h2>{selected ? 'Edit supplier' : 'Add supplier'}</h2>
        <form aria-label="Supplier details" onSubmit={saveSupplier}>
          <FormField label="Name" error={fieldErrors.name}>
            {(props) => (
              <input
                {...props}
                required
                maxLength={200}
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            )}
          </FormField>
          <FormField label="Contact name" error={fieldErrors.contact_name}>
            {(props) => (
              <input
                {...props}
                value={contactName}
                onChange={(event) => setContactName(event.target.value)}
              />
            )}
          </FormField>
          <FormField label="Email" error={fieldErrors.email}>
            {(props) => (
              <input
                {...props}
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            )}
          </FormField>
          <FormField label="Phone" error={fieldErrors.phone}>
            {(props) => (
              <input {...props} value={phone} onChange={(event) => setPhone(event.target.value)} />
            )}
          </FormField>
          <FormField label="Address" error={fieldErrors.address}>
            {(props) => (
              <textarea
                {...props}
                value={address}
                onChange={(event) => setAddress(event.target.value)}
              />
            )}
          </FormField>
          <button type="submit">{selected ? 'Save supplier' : 'Create supplier'}</button>
          {selected?.is_active && (
            <button type="button" onClick={deactivateSupplier}>
              Deactivate supplier
            </button>
          )}
        </form>
      </section>
      {selected && (
        <section>
          <h2>{selected.name} product catalog</h2>
          <form aria-label="Supplier catalog item" onSubmit={saveCatalogItem}>
            {!editingEntry && (
              <FormField label="Product or variant" error={fieldErrors.product_id}>
                {(props) => (
                  <select
                    {...props}
                    required
                    value={productChoice}
                    onChange={(event) => setProductChoice(event.target.value)}
                  >
                    <option value="">Choose product</option>
                    {choices.map((choice) => (
                      <option key={choice.value} value={choice.value}>
                        {choice.label}
                      </option>
                    ))}
                  </select>
                )}
              </FormField>
            )}
            <FormField label="Supplier SKU" error={fieldErrors.supplier_sku}>
              {(props) => (
                <input
                  {...props}
                  value={supplierSku}
                  onChange={(event) => setSupplierSku(event.target.value)}
                />
              )}
            </FormField>
            <FormField label="Supplier price" error={fieldErrors.supplier_price}>
              {(props) => (
                <input
                  {...props}
                  type="number"
                  min="0"
                  step="0.01"
                  required
                  value={supplierPrice}
                  onChange={(event) => setSupplierPrice(event.target.value)}
                />
              )}
            </FormField>
            <button type="submit">{editingEntry ? 'Save catalog item' : 'Add catalog item'}</button>
            {editingEntry && (
              <button type="button" onClick={() => setEditingEntry(null)}>
                Cancel
              </button>
            )}
          </form>
          <DataTable
            caption={`${selected.name} product catalog`}
            columns={[
              { header: 'Product', cell: (row) => `${row.product_name} (${row.product_sku})` },
              { header: 'Supplier SKU', cell: (row) => row.supplier_sku ?? '—' },
              { header: 'Supplier price', cell: (row) => row.supplier_price },
              {
                header: 'Actions',
                cell: (row) => (
                  <>
                    <button
                      type="button"
                      onClick={() => {
                        setEditingEntry(row);
                        setSupplierSku(row.supplier_sku ?? '');
                        setSupplierPrice(row.supplier_price);
                      }}
                    >
                      Edit
                    </button>{' '}
                    <button type="button" onClick={() => removeCatalogItem(row)}>
                      Remove
                    </button>
                  </>
                ),
              },
            ]}
            rows={catalog}
            rowKey={(row) => row.id}
            emptyMessage="No products in this supplier catalog."
          />
        </section>
      )}
    </div>
  );
}
