import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { ApiError } from '../../api';
import { FormField } from '../../shell/components';
import { productApi, type Category, type Product, type ProductImage } from './api';

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
const MAX_IMAGE_BYTES = Number(import.meta.env.VITE_PRODUCT_IMAGE_MAX_BYTES ?? 5 * 1024 * 1024);

function detailErrors(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError)) return {};
  if (Object.keys(error.fields).length > 0 && 'field' in error.fields) {
    const field = error.fields.field;
    const message = error.fields.message;
    return typeof field === 'string' && typeof message === 'string' ? { [field]: message } : {};
  }
  return {};
}

export default function ProductFormPage() {
  const { id } = useParams();
  const location = useLocation();
  const editing = id !== undefined;
  const navigate = useNavigate();
  const [values, setValues] = useState<FormValues>(EMPTY);
  const [categories, setCategories] = useState<Category[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [imageError, setImageError] = useState('');
  const [images, setImages] = useState<ProductImage[]>([]);
  const fileInput = useRef<HTMLInputElement>(null);

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
      productApi
        .images(Number(id))
        .then(setImages)
        .catch(() => setError('Could not load product images.'));
    }
  }, [editing, id]);

  useEffect(() => {
    const state = location.state as { message?: string } | null;
    if (state?.message) {
      setMessage(state.message);
      window.history.replaceState({}, document.title);
    }
  }, [location.state]);

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
        navigate(`/products/${product.id}/edit`, {
          state: { message: 'Product added successfully' },
        });
      } else navigate(`/products/${product.id}/edit`);
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
    if (file.size > MAX_IMAGE_BYTES) {
      setImageError('Image is too large');
      return;
    }
    try {
      await productApi.upload(Number(id), file);
      setImages(await productApi.images(Number(id)));
      if (fileInput.current) fileInput.current.value = '';
      setImageError('');
    } catch (e) {
      setImageError(e instanceof ApiError ? e.message : 'Could not upload image.');
    }
  }

  async function removeImage(image: ProductImage) {
    try {
      await productApi.removeImage(image.id);
      setImages((current) => current.filter((item) => item.id !== image.id));
    } catch (e) {
      setImageError(e instanceof ApiError ? e.message : 'Could not delete image.');
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
                  {category.path_label}
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
      {editing && (
        <FormField label="Product image" error={imageError}>
          {(props) => (
            <input
              {...props}
              ref={fileInput}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
            />
          )}
        </FormField>
      )}
      {images.length > 0 && (
        <div className="product-images">
          {images.map((image) => (
            <div key={image.id}>
              <img src={`/api${image.url}`} alt="Product" />
              <button type="button" onClick={() => removeImage(image)}>
                Delete image
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
