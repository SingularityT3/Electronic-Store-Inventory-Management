import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ApiError } from '../../api';
import { ConfirmDialog } from '../../shell/components';
import { can, useAuth } from '../auth';
import { productApi, type Product, type ProductImage } from './api';

const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' });

export default function ProductViewPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [product, setProduct] = useState<Product | null>(null);
  const [images, setImages] = useState<ProductImage[]>([]);
  const [error, setError] = useState('');
  const [confirm, setConfirm] = useState(false);

  useEffect(() => {
    productApi
      .get(Number(id))
      .then(setProduct)
      .catch(() => setError('Could not load product.'));
    productApi
      .images(Number(id))
      .then(setImages)
      .catch(() => setError('Could not load product images.'));
  }, [id]);

  async function remove() {
    try {
      await productApi.remove(Number(id));
      navigate('/products');
    } catch (e) {
      setConfirm(false);
      setError(e instanceof ApiError ? e.message : 'Could not delete product.');
    }
  }

  if (!product)
    return (
      <div className="page">
        {error ? (
          <p role="alert" className="error">
            {error}
          </p>
        ) : (
          'Loading...'
        )}
      </div>
    );
  return (
    <div className="page">
      <header className="page-header">
        <h1>{product.name}</h1>
        {can(user, 'products.manage') && (
          <span>
            <Link to={`/products/${product.id}/edit`}>Edit</Link>{' '}
            <button type="button" onClick={() => setConfirm(true)}>
              Delete
            </button>
          </span>
        )}
      </header>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <dl>
        <dt>SKU</dt>
        <dd>{product.sku}</dd>
        <dt>Category</dt>
        <dd>{product.category_name}</dd>
        <dt>Brand</dt>
        <dd>{product.brand}</dd>
        <dt>Price</dt>
        <dd>{money.format(Number(product.price))}</dd>
        <dt>Description</dt>
        <dd>{product.description || '—'}</dd>
      </dl>
      <div className="product-images">
        {images.map((image) => (
          <img key={image.id} src={`/api${image.url}`} alt={`${product.name} product`} />
        ))}
      </div>
      <ConfirmDialog
        open={confirm}
        title="Delete product"
        message={`Delete ${product.name}?`}
        confirmLabel="Delete"
        onConfirm={remove}
        onCancel={() => setConfirm(false)}
      />
    </div>
  );
}
