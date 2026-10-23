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
  variant_count: number;
  stock: number;
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

export interface CategoryAttribute {
  id: number;
  category_id: number;
  name: string;
  position: number;
  allowed_values: string[] | null;
}

export interface ProductVariant {
  id: number;
  product_id: number;
  sku: string;
  attributes: Record<string, string>;
  display_attributes: string[];
  price: string | null;
  effective_price: string;
  stock: number;
}

export const productApi = {
  list: (page = 1, pageSize = 50, q = '') =>
    api<ProductPage>(
      `/product?page=${page}&page_size=${pageSize}${q ? `&q=${encodeURIComponent(q)}` : ''}`,
    ),
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
  variants: (id: number) => api<ProductVariant[]>(`/product/${id}/variants`),
  createVariant: (id: number, body: object) =>
    api<ProductVariant>(`/product/${id}/variants`, { method: 'POST', body }),
  updateVariant: (productId: number, variantId: number, body: object) =>
    api<ProductVariant>(`/product/${productId}/variants/${variantId}`, {
      method: 'PATCH',
      body,
    }),
  removeVariant: (productId: number, variantId: number) =>
    api(`/product/${productId}/variants/${variantId}`, { method: 'DELETE' }),
  attributes: (id: number) => api<CategoryAttribute[]>(`/product/categories/${id}/attributes`),
  createAttribute: (id: number, body: object) =>
    api<CategoryAttribute>(`/product/categories/${id}/attributes`, { method: 'POST', body }),
  updateAttribute: (categoryId: number, id: number, body: object) =>
    api<CategoryAttribute>(`/product/categories/${categoryId}/attributes/${id}`, {
      method: 'PATCH',
      body,
    }),
  removeAttribute: (categoryId: number, id: number) =>
    api(`/product/categories/${categoryId}/attributes/${id}`, { method: 'DELETE' }),
};
