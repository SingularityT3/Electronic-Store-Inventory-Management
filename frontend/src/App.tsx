import { Route, Routes } from 'react-router-dom';
import { AuditLogPage } from './modules/audit';
import { ForgotPasswordPage, LoginPage, RequireAuth, ResetPasswordPage } from './modules/auth';
import { ProductFormPage, ProductListPage, ProductViewPage } from './modules/product';
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
          element={
            <RequirePermission permission="products.manage" what="product management">
              <ProductListPage />
            </RequirePermission>
          }
          path="/products"
        />
        <Route
          element={
            <RequirePermission permission="products.manage" what="product management">
              <ProductFormPage />
            </RequirePermission>
          }
          path="/products/new"
        />
        <Route
          element={
            <RequirePermission permission="products.manage" what="product management">
              <ProductFormPage />
            </RequirePermission>
          }
          path="/products/:id/edit"
        />
        <Route
          element={
            <RequirePermission permission="products.manage" what="product management">
              <ProductViewPage />
            </RequirePermission>
          }
          path="/products/:id"
        />
        {NAV_ITEMS.flatMap((item) => {
          // Feature items replace the placeholder with their screen. `path/*` keeps the
          // guard on any sub-page a feature adds later (e.g. /products/new).
          if (item.path === '/products') return [];
          const screen =
            item.path === '/audit' ? <AuditLogPage /> : <PlaceholderPage title={item.label} />;
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
