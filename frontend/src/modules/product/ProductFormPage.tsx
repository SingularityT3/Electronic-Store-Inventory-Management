import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ApiError } from '../../api';
import { FormField } from '../../shell/components';
import { productApi, type Category, type Product } from './api';

interface FormValues {
  name: string;
  sku: string;
  category_id: string;
  brand: string;
  price: string;
  description: string;
}

const EMPTY: FormValues = {
  name: '',
  sku: '',
  category_id: '',
  brand: '',
  price: '',
  description: '',
};

function detailErrors(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError)) return {};
  try {
    const detail = JSON.parse(error.message) as { field?: string; message?: string };
    return detail.field && detail.message ? { [detail.field]: detail.message } : {};
  } catch {
    return {};
  }
}

export default function ProductFormPage() {
  const { id } = useParams();
  const editing = id !== undefined;
  const navigate = useNavigate();
  const [values, setValues] = useState<FormValues>(EMPTY);
  const [categories, setCategories] = useState<Category[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [imageError, setImageError] = useState('');
  const [savedId, setSavedId] = useState<number | null>(null);

  useEffect(() => {
    productApi
      .categories()
      .then(setCategories)
      .catch(() => setError('Could not load categories.'));
    if (editing) {
      productApi
        .get(Number(id))
        .then((product: Product) =>
          setValues({
            name: product.name,
            sku: product.sku,
            category_id: String(product.category_id),
            brand: product.brand,
            price: product.price,
            description: product.description ?? '',
          }),
        )
        .catch(() => setError('Could not load product.'));
    }
  }, [editing, id]);

  function update(field: keyof FormValues, value: string) {
    setValues({ ...values, [field]: value });
    setErrors({ ...errors, [field]: '' });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError('');
    setErrors({});
    try {
      const body = { ...values, category_id: Number(values.category_id), price: values.price };
      const product = editing
        ? await productApi.update(Number(id), body)
        : await productApi.create(body);
      if (!editing) {
        setMessage('Product added successfully');
        setSavedId(product.id);
      } else navigate(`/products/${product.id}`);
    } catch (e) {
      const mapped = detailErrors(e);
      if (Object.keys(mapped).length) setErrors(mapped);
      else setError(e instanceof ApiError ? e.message : 'Could not save product.');
    }
  }

  async function upload(file: File) {
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      setImageError('Only JPEG, PNG and WebP images are allowed');
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setImageError('Image is too large');
      return;
    }
    try {
      await productApi.upload(Number(id ?? savedId), file);
      setImageError('');
    } catch (e) {
      setImageError(e instanceof ApiError ? e.message : 'Could not upload image.');
    }
  }

  return (
    <div className="page">
      <h1>{editing ? 'Edit product' : 'Add product'}</h1>
      {message && <p role="status">{message}</p>}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <form onSubmit={submit}>
        <FormField label="Product name" error={errors.name}>
          {(props) => (
            <input
              {...props}
              value={values.name}
              onChange={(e) => update('name', e.target.value)}
            />
          )}
        </FormField>
        <FormField label="SKU" error={errors.sku}>
          {(props) => (
            <input {...props} value={values.sku} onChange={(e) => update('sku', e.target.value)} />
          )}
        </FormField>
        <FormField label="Category" error={errors.category_id}>
          {(props) => (
            <select
              {...props}
              value={values.category_id}
              onChange={(e) => update('category_id', e.target.value)}
            >
              <option value="">Select category</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
          )}
        </FormField>
        <FormField label="Brand" error={errors.brand}>
          {(props) => (
            <input
              {...props}
              value={values.brand}
              onChange={(e) => update('brand', e.target.value)}
            />
          )}
        </FormField>
        <FormField label="Price" error={errors.price}>
          {(props) => (
            <input
              {...props}
              type="number"
              min="0"
              step="0.01"
              value={values.price}
              onChange={(e) => update('price', e.target.value)}
            />
          )}
        </FormField>
        <FormField label="Description" error={errors.description}>
          {(props) => (
            <textarea
              {...props}
              value={values.description}
              onChange={(e) => update('description', e.target.value)}
            />
          )}
        </FormField>
        <button type="submit">{editing ? 'Save changes' : 'Add product'}</button>
      </form>
      {(editing || savedId !== null) && (
        <FormField label="Product image" error={imageError}>
          {(props) => (
            <input
              {...props}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
            />
          )}
        </FormField>
      )}
    </div>
  );
}
