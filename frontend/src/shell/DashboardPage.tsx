import { Link } from 'react-router-dom';
import { can, useAuth } from '../modules/auth';
import { ROLE_NAMES } from './UserMenu';

const TASKS = [
  { permission: 'sales.record' as const, label: 'Start a sale', path: '/sales' },
  { permission: 'sales.record' as const, label: 'Process a return', path: '/returns' },
  { permission: 'products.view' as const, label: 'Find a product', path: '/products/search' },
  { permission: 'stock.view' as const, label: 'View stock', path: '/stock' },
  { permission: 'stock.adjust' as const, label: 'Adjust stock', path: '/stock/adjust' },
  {
    permission: 'purchase_orders.receive' as const,
    label: 'Receive a purchase order',
    path: '/purchase-orders/receive',
  },
  { permission: 'stock.transfer' as const, label: 'Transfer stock', path: '/stock/transfer' },
  { permission: 'reports.view' as const, label: 'View reports', path: '/reports' },
];

/** Landing screen after sign in. The menu on the left lists what this role can do. */
export default function DashboardPage() {
  const { user } = useAuth();
  if (!user) return null;
  const tasks = TASKS.filter((task) => can(user, task.permission));
  return (
    <div className="page">
      <h1>{ROLE_NAMES[user.role]} dashboard</h1>
      <p>Welcome, {user.full_name}. Choose what you want to do from the menu on the left.</p>
      <section aria-labelledby="common-tasks-heading">
        <h2 id="common-tasks-heading">Common tasks</h2>
        <div className="common-tasks">
          {tasks.map((task) => (
            <Link key={task.path} className="common-task" to={task.path}>
              {task.label}
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
