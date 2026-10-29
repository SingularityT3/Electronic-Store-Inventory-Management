import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { AccessDenied, Breadcrumb, ConfirmDialog, DataTable, EmptyState, FormField } from '.';

interface Product {
  sku: string;
  name: string;
}

const columns = [
  { header: 'SKU', cell: (p: Product) => p.sku },
  { header: 'Name', cell: (p: Product) => p.name },
];

test('DataTable lists a row per record under its headers', () => {
  render(
    <DataTable
      caption="Products"
      columns={columns}
      rows={[
        { sku: 'TV-001', name: 'Television' },
        { sku: 'PH-002', name: 'Phone' },
      ]}
      rowKey={(p) => p.sku}
      emptyMessage="No products found"
    />,
  );
  expect(screen.getByRole('table', { name: 'Products' })).toBeInTheDocument();
  expect(screen.getAllByRole('columnheader').map((h) => h.textContent)).toEqual(['SKU', 'Name']);
  expect(screen.getAllByRole('row')).toHaveLength(3);
  expect(screen.getByText('Television')).toBeInTheDocument();
});

test('DataTable shows the empty state when there are no rows', () => {
  render(
    <DataTable
      caption="Products"
      columns={columns}
      rows={[]}
      rowKey={(p: Product) => p.sku}
      emptyMessage="No products found"
    />,
  );
  expect(screen.getByText('No products found')).toBeInTheDocument();
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
});

test('EmptyState shows its message and any action', () => {
  render(
    <EmptyState message="No suppliers found">
      <button>Add supplier</button>
    </EmptyState>,
  );
  expect(screen.getByText('No suppliers found')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Add supplier' })).toBeInTheDocument();
});

test('FormField labels its control and announces a validation message', () => {
  render(
    <FormField label="SKU" hint="Letters and digits" error="SKU already exists">
      {(control) => <input {...control} />}
    </FormField>,
  );
  const input = screen.getByLabelText('SKU');
  expect(input).toHaveAttribute('aria-invalid', 'true');
  expect(input).toHaveAccessibleDescription('Letters and digits SKU already exists');
  expect(screen.getByRole('alert')).toHaveTextContent('SKU already exists');
});

test('FormField without an error is valid and silent', () => {
  render(<FormField label="Name">{(control) => <input {...control} />}</FormField>);
  expect(screen.getByLabelText('Name')).toHaveAttribute('aria-invalid', 'false');
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

function dialog(overrides: Partial<Parameters<typeof ConfirmDialog>[0]> = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  render(
    <ConfirmDialog
      open
      title="Delete product?"
      message="This cannot be undone."
      confirmLabel="Delete"
      onConfirm={onConfirm}
      onCancel={onCancel}
      {...overrides}
    />,
  );
  return { onConfirm, onCancel };
}

test('ConfirmDialog asks, and starts on the safe choice', () => {
  dialog();
  expect(screen.getByRole('alertdialog', { name: 'Delete product?' })).toHaveAccessibleDescription(
    'This cannot be undone.',
  );
  expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus();
});

test('ConfirmDialog confirms only when asked', async () => {
  const { onConfirm, onCancel } = dialog();
  await userEvent.click(screen.getByRole('button', { name: 'Delete' }));
  expect(onConfirm).toHaveBeenCalledTimes(1);
  expect(onCancel).not.toHaveBeenCalled();
});

test('ConfirmDialog cancels on Cancel and on Escape', async () => {
  const { onConfirm, onCancel } = dialog();
  await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  await userEvent.keyboard('{Escape}');
  expect(onCancel).toHaveBeenCalledTimes(2);
  expect(onConfirm).not.toHaveBeenCalled();
});

test('ConfirmDialog keeps Tab inside the dialog', async () => {
  dialog();
  await userEvent.tab();
  expect(screen.getByRole('button', { name: 'Delete' })).toHaveFocus();
  await userEvent.tab();
  expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus();
});

test('ConfirmDialog renders custom children and keeps Tab inside', async () => {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  render(
    <ConfirmDialog
      open
      title="Approve override"
      confirmLabel="Approve"
      onConfirm={onConfirm}
      onCancel={onCancel}
    >
      <input data-testid="override-input" type="text" placeholder="Username" />
    </ConfirmDialog>,
  );
  expect(screen.getByTestId('override-input')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus();
  await userEvent.tab();
  expect(screen.getByRole('button', { name: 'Approve' })).toHaveFocus();
  await userEvent.tab();
  expect(screen.getByTestId('override-input')).toHaveFocus();
  await userEvent.tab();
  expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus();
});

test('a closed ConfirmDialog renders nothing', () => {
  dialog({ open: false });
  expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
});

test('Breadcrumb exposes an accessible navigation trail', () => {
  render(
    <MemoryRouter>
      <Breadcrumb
        items={[
          { label: 'Electronics', to: '/categories?selected=1' },
          { label: 'Mobile Phones', to: '/categories?selected=2' },
          { label: 'Smartphones' },
        ]}
      />
    </MemoryRouter>,
  );
  expect(screen.getByRole('navigation', { name: 'Breadcrumb' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Mobile Phones' })).toHaveAttribute(
    'href',
    '/categories?selected=2',
  );
  expect(screen.getByText('Smartphones')).toHaveAttribute('aria-current', 'page');
});

test('AccessDenied says what is blocked and links back to the dashboard', () => {
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AccessDenied what="supplier management" />
    </MemoryRouter>,
  );
  expect(screen.getByRole('heading', { name: 'Access denied' })).toBeInTheDocument();
  expect(screen.getByRole('alert')).toHaveTextContent(
    'You do not have permission to view supplier management.',
  );
  expect(screen.getByRole('link', { name: 'Back to dashboard' })).toHaveAttribute('href', '/');
});
