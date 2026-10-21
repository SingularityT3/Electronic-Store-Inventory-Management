import { Route, Routes } from 'react-router-dom';
import { AuditLogPage } from './modules/audit';
import {
  ForgotPasswordPage,
  HomePage,
  LoginPage,
  RequireAuth,
  ResetPasswordPage,
} from './modules/auth';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route
        path="/audit"
        element={
          <RequireAuth>
            <AuditLogPage />
          </RequireAuth>
        }
      />
      {/* Every other URL is internal and needs a signed-in user (FR-5.2). */}
      <Route
        path="*"
        element={
          <RequireAuth>
            <HomePage />
          </RequireAuth>
        }
      />
    </Routes>
  );
}
