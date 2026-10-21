import type { ReactNode } from 'react';
import { can, useAuth, type Permission } from '../../modules/auth';
import AccessDenied from './AccessDenied';

/**
 * Renders its children only if the signed-in role holds `permission`; otherwise the access-denied
 * page. Cosmetic like the menu: the API enforces the same rule (NFR-7). Use inside `RequireAuth`.
 */
export default function RequirePermission({
  permission,
  what,
  children,
}: {
  permission: Permission;
  what: string;
  children: ReactNode;
}) {
  const { user } = useAuth();
  return can(user, permission) ? children : <AccessDenied what={what} />;
}
