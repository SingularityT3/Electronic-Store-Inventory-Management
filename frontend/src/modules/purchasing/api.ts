import { api } from '../../api';

export interface Supplier {
  id: number;
  name: string;
  contact_name: string | null;
  email: string | null;
  phone: string | null;
  address: string | null;
  is_active: boolean;
}

export interface SupplierProduct {
  id: number;
  supplier_id: number;
  product_id: number;
  variant_id: number | null;
  supplier_sku: string | null;
  supplier_price: string;
  product_name: string;
  product_sku: string;
}

export interface CatalogItemInput {
  product_id: number;
  variant_id: number | null;
  supplier_sku: string | null;
  supplier_price: string;
}

export const purchasingApi = {
  suppliers: (activeOnly = false) =>
    api<Supplier[]>(`/purchasing/suppliers${activeOnly ? '?active_only=true' : ''}`),
  createSupplier: (body: Omit<Supplier, 'id' | 'is_active'>) =>
    api<Supplier>('/purchasing/suppliers', { method: 'POST', body }),
  updateSupplier: (id: number, body: Partial<Omit<Supplier, 'id' | 'is_active'>>) =>
    api<Supplier>(`/purchasing/suppliers/${id}`, { method: 'PATCH', body }),
  deactivateSupplier: (id: number) => api(`/purchasing/suppliers/${id}`, { method: 'DELETE' }),
  supplierProducts: (id: number) => api<SupplierProduct[]>(`/purchasing/suppliers/${id}/products`),
  addSupplierProduct: (id: number, body: CatalogItemInput) =>
    api<SupplierProduct>(`/purchasing/suppliers/${id}/products`, { method: 'POST', body }),
  updateSupplierProduct: (
    supplierId: number,
    entryId: number,
    body: { supplier_sku: string | null; supplier_price: string },
  ) =>
    api<SupplierProduct>(`/purchasing/suppliers/${supplierId}/products/${entryId}`, {
      method: 'PATCH',
      body,
    }),
  removeSupplierProduct: (supplierId: number, entryId: number) =>
    api(`/purchasing/suppliers/${supplierId}/products/${entryId}`, { method: 'DELETE' }),
};
