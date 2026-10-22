import { api } from '../../api';

export interface Product {
  id: number;
  name: string;
  sku: string;
  category_id: number;
  category_name: string;
  brand: string;
  price: string;
  description: string | null;
  is_active: boolean;
}

export interface Category {
  id: number;
  name: string;
  parent_id: number | null;
}

export interface ProductPage {
  items: Product[];
  total: number;
  page: number;
  page_size: number;
}

export interface ProductImage {
  id: number;
  url: string;
}

export const productApi = {
  list: (page = 1, pageSize = 50) =>
    api<ProductPage>(`/product?page=${page}&page_size=${pageSize}`),
  get: (id: number) => api<Product>(`/product/${id}`),
  categories: () => api<Category[]>('/product/categories'),
  create: (body: object) => api<Product>('/product', { method: 'POST', body }),
  update: (id: number, body: object) => api<Product>(`/product/${id}`, { method: 'PUT', body }),
  remove: (id: number) => api(`/product/${id}`, { method: 'DELETE' }),
  images: (id: number) => api<ProductImage[]>(`/product/${id}/images`),
  upload: (id: number, file: File) => {
    const body = new FormData();
    body.append('file', file);
    return api<ProductImage>(`/product/${id}/images`, { method: 'POST', body });
  },
  removeImage: (id: number) => api(`/product/images/${id}`, { method: 'DELETE' }),
};
