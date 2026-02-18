import { Eye, ShieldAlert } from "lucide-react";
import AdminPageHeader from "./components/AdminPageHeader";
import { users } from "./data";
import { useAdminToast } from "./AdminToastContext";

export default function AdminUsers() {
  const { pushToast } = useAdminToast();

  return (
    <>
      <AdminPageHeader
        title="Manage Users"
        subtitle="Monitor user registrations, roles, and account status."
      />

      <section className="admin-card">
        <div className="d-flex flex-wrap gap-2 justify-content-between align-items-center mb-3">
          <div className="d-flex gap-2 flex-wrap">
            <input className="form-control" placeholder="Search user" />
            <select className="form-select">
              <option>Role</option>
              <option>Customer</option>
              <option>Vendor</option>
              <option>Admin</option>
            </select>
            <select className="form-select">
              <option>Status</option>
              <option>Active</option>
              <option>Blocked</option>
            </select>
          </div>
          <div className="text-muted small">{users.length} users</div>
        </div>
        <div className="table-responsive">
          <table className="table admin-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Phone</th>
                <th>Role</th>
                <th>Status</th>
                <th>Registered</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id}>
                  <td>
                    <div className="fw-semibold">{user.name}</div>
                    <small className="text-muted">{user.id}</small>
                  </td>
                  <td>{user.email}</td>
                  <td>{user.phone}</td>
                  <td>{user.role}</td>
                  <td>
                    <span
                      className={`badge-soft ${user.status === "Active" ? "success" : "danger"}`}
                    >
                      {user.status}
                    </span>
                  </td>
                  <td>{user.registeredAt}</td>
                  <td>
                    <div className="d-flex gap-2">
                      <button type="button" className="btn btn-outline-light btn-sm" title="View details">
                        <Eye size={16} />
                      </button>
                      <button
                        type="button"
                        className="btn btn-outline-light btn-sm"
                        title="Block/Unblock user"
                        onClick={() =>
                          pushToast({
                            title: "User status updated",
                            message: `${user.name} has been reviewed.`,
                          })
                        }
                      >
                        <ShieldAlert size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <nav className="d-flex justify-content-between align-items-center mt-3">
          <span className="text-muted small">Page 1 of 1</span>
          <ul className="pagination mb-0">
            <li className="page-item disabled"><span className="page-link">Prev</span></li>
            <li className="page-item active"><span className="page-link">1</span></li>
            <li className="page-item disabled"><span className="page-link">Next</span></li>
          </ul>
        </nav>
      </section>
    </>
  );
}
