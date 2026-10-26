import { api } from '../../api';

export interface Availability {
  product_id: number;
  product_name: string;
  sku: string;
  variant_id: number | null;
  variant_sku: string | null;
  variant_attributes: Record<string, unknown> | null;
  location_id: number;
  location_name: string;
  available_quantity: number;
  unit_price?: string;
}

export interface Sale {
  id: number;
  location_id: number;
  cashier_id: number;
  sold_at: string;
  subtotal: string;
  discount_total: string;
  tax_total: string;
  total: string;
  customer_name: string | null;
  lines: {
    id: number;
    product_id: number;
    variant_id: number | null;
    quantity: number;
    unit_price: string;
    discount_amount: string;
    tax_amount: string;
    line_total: string;
  }[];
  payments: { id: number; method: string; amount: string; reference: string | null }[];
  invoice: { invoice_number: number; issued_at: string; total: string };
}

export const salesApi = {
  availability: (locationId: number, productIds: number[]) => {
    const params = new URLSearchParams({ location_id: String(locationId), limit: '100' });
    productIds.forEach((id) => params.append('ids', String(id)));
    return api<Availability[]>(`/sales/availability?${params}`);
  },
  create: (body: object) => api<Sale>('/sales', { method: 'POST', body }),
  get: (id: number) => api<Sale>(`/sales/${id}`),
};
