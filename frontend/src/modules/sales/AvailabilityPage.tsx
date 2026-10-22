import { useEffect, useState } from 'react';
import { api, ApiError } from '../../api';
import { DataTable } from '../../shell/components';
import { useAuth } from '../auth';

interface Location {
  id: number;
  name: string;
  type: string;
}

interface Availability {
  product_id: number;
  product_name: string;
  sku: string;
  variant_id: number | null;
  variant_sku: string | null;
  variant_attributes: Record<string, unknown> | null;
  location_id: number;
  location_name: string;
  available_quantity: number;
}

function itemName(row: Availability): string {
  return row.variant_sku ? `${row.product_name} (${row.variant_sku})` : row.product_name;
}

export default function SalesAvailabilityPage() {
  const { user } = useAuth();
  const canChooseLocation = user?.role === 'admin' || user?.role === 'manager';
  const [locations, setLocations] = useState<Location[]>([]);
  const [locationId, setLocationId] = useState('');
  const [availability, setAvailability] = useState<Availability[]>([]);
  const [loadingLocations, setLoadingLocations] = useState(true);
  const [loadingAvailability, setLoadingAvailability] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let current = true;
    if (!canChooseLocation) {
      if (user?.location_id !== null && user?.location_id !== undefined) {
        setLocationId(String(user.location_id));
      }
      setLoadingLocations(false);
      return () => {
        current = false;
      };
    }
    api<Location[]>('/stock/locations')
      .then((rows) => {
        if (!current) return;
        setLocations(rows);
      })
      .catch((cause: unknown) => {
        if (current) {
          setError(cause instanceof ApiError ? cause.message : 'Could not load locations.');
        }
      })
      .finally(() => {
        if (current) setLoadingLocations(false);
      });
    return () => {
      current = false;
    };
  }, [canChooseLocation, user?.location_id]);

  useEffect(() => {
    if (!user || loadingLocations || !locationId) return;
    let current = true;
    setLoadingAvailability(true);
    setError('');
    const query = locationId ? `?location_id=${encodeURIComponent(locationId)}` : '';
    api<Availability[]>(`/sales/availability${query}`)
      .then((rows) => current && setAvailability(rows))
      .catch((cause: unknown) => {
        if (!current) return;
        setAvailability([]);
        setError(cause instanceof ApiError ? cause.message : 'Could not load availability.');
      })
      .finally(() => {
        if (current) setLoadingAvailability(false);
      });
    return () => {
      current = false;
    };
  }, [locationId, loadingLocations, user]);

  return (
    <div className="page">
      <header className="page-header">
        <h1>Sales availability</h1>
      </header>
      {canChooseLocation && (
        <label>
          Location
          <select
            aria-label="Location"
            value={locationId}
            onChange={(event) => setLocationId(event.target.value)}
            disabled={loadingLocations}
          >
            <option value="">Choose a location</option>
            {locations.map((location) => (
              <option key={location.id} value={location.id}>
                {location.name}
              </option>
            ))}
          </select>
        </label>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {loadingAvailability ? (
        <p className="loading">Loading availability…</p>
      ) : (
        <DataTable
          caption="Point-of-sale stock availability"
          columns={[
            { header: 'Product', cell: itemName },
            { header: 'SKU', cell: (row) => row.variant_sku ?? row.sku },
            { header: 'Location', cell: (row) => row.location_name },
            { header: 'Available', cell: (row) => row.available_quantity },
          ]}
          rows={availability}
          rowKey={(row) => `${row.product_id}-${row.variant_id ?? 'product'}`}
          emptyMessage="No stock is recorded for this location."
        />
      )}
    </div>
  );
}
