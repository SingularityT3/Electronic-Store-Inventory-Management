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
  invoice: {
    invoice_number: number;
    invoice_label: string;
    issued_at: string;
    total: string;
    content: DocumentContent;
  };
  return_status?: 'none' | 'partially_returned' | 'fully_returned';
}

export interface SaleLookupLine {
  id: number;
  product_id: number;
  product_name: string;
  sku: string;
  variant_id: number | null;
  variant_sku: string | null;
  variant_attributes: Record<string, unknown> | null;
  quantity: number;
  unit_price: string;
  discount_amount: string;
  tax_amount: string;
  line_total: string;
  serial_numbers: string[];
  quantity_returned: number;
  quantity_returnable: number;
  returnable_serials: string[];
  returnable_serial_ids: number[];
}

export interface SaleLookup {
  id: number;
  location_id: number;
  location_name: string;
  cashier_id: number;
  sold_at: string;
  subtotal: string;
  discount_total: string;
  tax_total: string;
  total: string;
  customer_name: string | null;
  lines: SaleLookupLine[];
  days_since_sale: number;
  return_window_days: number;
  requires_manager_approval: boolean;
  return_status: 'none' | 'partially_returned' | 'fully_returned';
  invoice: {
    invoice_number: number;
    invoice_label: string;
    issued_at: string;
    total: string;
  };
}

export interface ReturnLineInput {
  sale_line_id: number;
  quantity: number;
  condition: 'resaleable' | 'damaged';
  serial_number_ids?: number[];
}

export interface ManagerApprovalInput {
  username: string;
  password: string;
}

export interface ReturnInput {
  invoice_number: string | number;
  lines: ReturnLineInput[];
  reason: string;
  manager_approval?: ManagerApprovalInput;
}

export interface ReturnCreditNoteLine {
  id: number;
  sale_line_id: number;
  product_id: number;
  product_name: string;
  sku: string;
  variant_id: number | null;
  variant_sku: string | null;
  quantity: number;
  condition: string;
  restocked: boolean;
  refund_amount: string;
  serial_numbers: string[];
}

export interface ReturnCreditNote {
  return_id: number;
  credit_note_number: string;
  sale_id: number;
  invoice_number: number;
  created_at: string;
  location_id: number;
  location_name: string;
  processed_by_username: string;
  approved_by_username: string | null;
  reason: string;
  refund_total: string;
  non_sellable_quantity: number;
  lines: ReturnCreditNoteLine[];
  content?: DocumentContent;
}

export interface DocumentContent {
  kind: 'invoice' | 'credit_note';
  invoice_number?: number;
  invoice_label?: string;
  credit_note_number?: string;
  return_id?: number;
  issued_at?: string;
  created_at?: string;
  store_name: string;
  store_gstin?: string | null;
  location_name: string;
  location_address?: string | null;
  cashier_id?: number;
  cashier_name?: string;
  processor_name?: string;
  customer_name?: string | null;
  gst_rate?: string;
  subtotal?: string;
  discount_total?: string;
  tax_total?: string;
  total?: string;
  refund_total?: string;
  reason?: string;
  lines: {
    id?: number;
    product_name: string;
    sku: string;
    variant_label?: string | null;
    quantity: number;
    unit_price?: string;
    discount?: string;
    tax?: string;
    line_total?: string;
    refund_amount?: string;
    serial_numbers?: string[];
  }[];
  payments?: { method: string; amount: string; reference?: string | null }[];
}

export interface InvoiceDocument {
  content: DocumentContent;
  return_status: 'none' | 'partially_returned' | 'fully_returned';
  credit_notes: {
    credit_note_number: string;
    return_id: number;
    created_at: string;
    refund_total: string;
  }[];
}

export interface SalesHistoryItem {
  sale_id: number;
  invoice_number: number;
  invoice_label: string;
  sold_at: string;
  cashier_name: string;
  location_id: number;
  location_name: string;
  total: string;
  return_status: 'none' | 'partially_returned' | 'fully_returned';
}

export interface SalesHistory {
  items: SalesHistoryItem[];
  total: number;
  page: number;
  page_size: number;
}

export const salesApi = {
  availability: (locationId: number, productIds: number[]) => {
    const params = new URLSearchParams({ location_id: String(locationId), limit: '100' });
    productIds.forEach((id) => params.append('ids', String(id)));
    return api<Availability[]>(`/sales/availability?${params}`);
  },
  create: (body: object) => api<Sale>('/sales', { method: 'POST', body }),
  get: (id: number) => api<Sale>(`/sales/${id}`),
  lookupByInvoice: (invoiceNumber: string | number) =>
    api<SaleLookup>(`/sales/by-invoice/${encodeURIComponent(String(invoiceNumber).trim())}`),
  processReturn: (body: ReturnInput) =>
    api<ReturnCreditNote>('/sales/returns', { method: 'POST', body }),
  getCreditNote: (returnId: number) => api<ReturnCreditNote>(`/sales/returns/${returnId}`),
  getInvoiceDocument: (invoiceNumber: string | number) =>
    api<InvoiceDocument>(`/sales/invoices/${encodeURIComponent(String(invoiceNumber))}`),
  history: (params: URLSearchParams) => api<SalesHistory>(`/sales/history?${params}`),
};
