import { api } from '../../api';

export interface Product {
  id: number;
  name: string;
  sku: string;
  category_id: number;
  category_name: string;
  category_path: { id: number; name: string }[];
  category_path_label: string;
  brand: string;
  price: string;
  description: string | null;
  is_active: boolean;
}

export interface Category {
  id: number;
  name: string;
  parent_id: number | null;
  depth: number;
  path: { id: number; name: string }[];
  path_label: string;
  product_count: number;
  total_product_count: number;
}

export interface CategoryProduct {
  id: number;
  name: string;
  sku: string;
  brand: string;
  price: string;
  category_path: { id: number; name: string }[];
  category_path_label: string;
}

export interface CategoryProductPage {
  items: CategoryProduct[];
  total: number;
  page: number;
  page_size: number;
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
  category: (id: number) => api<Category>(`/product/categories/${id}`),
  categoryProducts: (id: number, page = 1, pageSize = 50) =>
    api<CategoryProductPage>(
      `/product/categories/${id}/products?page=${page}&page_size=${pageSize}`,
    ),
  createCategory: (body: { name: string; parent_id: number | null }) =>
    api<Category>('/product/categories', { method: 'POST', body }),
  updateCategory: (id: number, body: { name?: string; parent_id?: number | null }) =>
    api<Category>(`/product/categories/${id}`, { method: 'PATCH', body }),
  removeCategory: (id: number) => api(`/product/categories/${id}`, { method: 'DELETE' }),
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
