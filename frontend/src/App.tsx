import { Route, Routes } from 'react-router-dom';
import { AuditLogPage } from './modules/audit';
import {
  ForgotPasswordPage,
  LoginPage,
  RequireAuth,
  ResetPasswordPage,
  UsersPage,
} from './modules/auth';
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
        {NAV_ITEMS.flatMap((item) => {
          // Feature items replace the placeholder with their screen. `path/*` keeps the
          // guard on any sub-page a feature adds later (e.g. /products/new).
          const screen =
            item.path === '/audit' ? (
              <AuditLogPage />
            ) : item.path === '/users' ? (
              <UsersPage />
            ) : item.path === '/stock' ? (
              <StockLevelsPage />
            ) : item.path === '/sales' ? (
              <SalesAvailabilityPage />
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
