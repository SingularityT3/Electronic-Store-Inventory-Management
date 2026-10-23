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
  ProductViewPage,
} from './modules/product';
import { SalesAvailabilityPage } from './modules/sales';
import { StockLevelsPage } from './modules/stock';
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
              <PlaceholderPage title="Product search" />
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
            ) : item.path === '/stock' ? (
              <StockLevelsPage />
            ) : item.path === '/sales' ? (
              <SalesAvailabilityPage />
            ) : item.path === '/categories' ? (
              <CategoriesPage />
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
