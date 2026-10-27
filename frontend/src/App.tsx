import { Route, Routes } from 'react-router-dom';
import { AuditLogPage } from './modules/audit';
import {
  ForgotPasswordPage,
  LoginPage,
  RequireAuth,
  ResetPasswordPage,
  UsersPage,
} from './modules/auth';
import {
  CategoriesPage,
  CategoryAttributesPage,
  ProductFormPage,
  ProductListPage,
  ProductSearchPage,
  ProductViewPage,
} from './modules/product';
import { PosPage } from './modules/sales';
import { LocationsPage, StockLevelsPage, StockTransferPage } from './modules/stock';
import { POReceivingPage, PurchaseOrdersPage, SuppliersPage } from './modules/purchasing';
import { AppLayout, DashboardPage, NAV_ITEMS, NotFoundPage, PlaceholderPage } from './shell';
import { RequirePermission } from './shell/components';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />

      {/* Every other URL is internal and needs a signed-in user (FR-5.2). */}
      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route index element={<DashboardPage />} />

        <Route
          path="/products"
          element={
            <RequirePermission permission="products.view" what="the product catalog">
              <ProductListPage />
            </RequirePermission>
          }
        />

        <Route
          path="/products/new"
          element={
            <RequirePermission permission="products.manage" what="product management">
              <ProductFormPage />
            </RequirePermission>
          }
        />

        <Route
          path="/products/search"
          element={
            <RequirePermission permission="products.view" what="product search">
              <ProductSearchPage />
            </RequirePermission>
          }
        />

        <Route
          path="/products/:id/edit"
          element={
            <RequirePermission permission="products.manage" what="product management">
              <ProductFormPage />
            </RequirePermission>
          }
        />

        <Route
          path="/products/:id"
          element={
            <RequirePermission permission="products.view" what="the product catalog">
              <ProductViewPage />
            </RequirePermission>
          }
        />

        <Route
          path="/categories/:id/attributes"
          element={
            <RequirePermission permission="products.manage" what="category management">
              <CategoryAttributesPage />
            </RequirePermission>
          }
        />

        {NAV_ITEMS.flatMap((item) => {
          // Feature items replace the placeholder with their screen.
          // `path/*` keeps the guard on any sub-page a feature adds later.
          if (item.path === '/products') return [];

          const screen =
            item.path === '/audit' ? (
              <AuditLogPage />
            ) : item.path === '/users' ? (
              <UsersPage />
            ) : item.path === '/stock' || item.path === '/stock/adjust' ? (
              // Adjustments start from a stock record (UC-08), so both items open stock levels.
              <StockLevelsPage />
            ) : item.path === '/locations' ? (
              <LocationsPage />
            ) : item.path === '/variants' ? (
              // Variants are managed on each product's page (UC-06).
              <ProductListPage
                title="Variants"
                intro="Open a product to add, edit or remove its variants."
              />
            ) : item.path === '/stock/transfer' ? (
              <StockTransferPage />
            ) : item.path === '/sales' ? (
              <PosPage />
            ) : item.path === '/categories' ? (
              <CategoriesPage />
            ) : item.path === '/suppliers' ? (
              <SuppliersPage />
            ) : item.path === '/purchase-orders' ? (
              <PurchaseOrdersPage />
            ) : item.path === '/purchase-orders/receive' ? (
              <POReceivingPage />
            ) : (
              <PlaceholderPage title={item.label} />
            );

          const guarded = (
            <RequirePermission permission={item.permission} what={item.deniedLabel}>
              {screen}
            </RequirePermission>
          );

          return [
            <Route key={item.path} path={item.path} element={guarded} />,
            <Route key={`${item.path}/*`} path={`${item.path}/*`} element={guarded} />,
          ];
        })}

        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
