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

export interface PurchaseOrderLine {
  id: number;
  product_id: number;
  product_name: string;
  sku: string;
  variant_id: number | null;
  quantity_ordered: number;
  quantity_received: number;
  unit_price: string;
  line_total: string;
}

export interface PurchaseOrder {
  id: number;
  po_number: string;
  supplier_id: number;
  supplier_name: string;
  location_id: number;
  status: 'draft' | 'submitted' | 'partially_received' | 'received' | 'cancelled';
  created_by: number;
  notes: string | null;
  expected_delivery_date: string | null;
  submitted_at: string | null;
  created_at: string;
  lines: PurchaseOrderLine[];
  total: string;
}

export interface PurchaseOrderLineInput {
  product_id: number;
  variant_id: number | null;
  quantity_ordered: number;
  unit_price: string;
}

export interface PurchaseOrderInput {
  supplier_id: number;
  location_id: number;
  expected_delivery_date: string;
  notes: string | null;
  lines: PurchaseOrderLineInput[];
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
  purchaseOrders: () => api<PurchaseOrder[]>('/purchasing/purchase-orders'),
  pendingPurchaseOrders: () => api<PurchaseOrder[]>('/purchasing/purchase-orders/pending'),
  purchaseOrder: (id: number) => api<PurchaseOrder>(`/purchasing/purchase-orders/${id}`),
  createPurchaseOrder: (body: PurchaseOrderInput) =>
    api<PurchaseOrder>('/purchasing/purchase-orders', { method: 'POST', body }),
  updatePurchaseOrder: (id: number, body: PurchaseOrderInput) =>
    api<PurchaseOrder>(`/purchasing/purchase-orders/${id}`, { method: 'PATCH', body }),
  submitPurchaseOrder: (id: number) =>
    api<PurchaseOrder>(`/purchasing/purchase-orders/${id}/submit`, { method: 'POST' }),
  cancelPurchaseOrder: (id: number) =>
    api<PurchaseOrder>(`/purchasing/purchase-orders/${id}/cancel`, { method: 'POST' }),
};
