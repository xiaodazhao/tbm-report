// src/components/Layout/Sidebar.jsx
import { Link, useLocation } from "react-router-dom";

export default function Sidebar() {
  const location = useLocation();

  const menu = [
    { name: "工况概览", path: "/" },
    { name: "围岩分析", path: "/geology" },
    { name: "气体监测", path: "/gas" },
    { name: "自动报告", path: "/report" },
    { name: "系统设置", path: "/settings" },
  ];

  return (
    <div
      style={{
        width: 240,
        background: "var(--card-bg)",
        borderRight: "1px solid var(--border)",
        padding: "20px 15px",
        flexShrink: 0,
      }}
    >
      <h2 style={{ fontSize: 22, marginBottom: 20 }}>TBM 面板</h2>

      <nav style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {menu.map((item) => (
          <Link
            key={item.path}
            to={item.path}
            className={location.pathname === item.path ? "active" : ""}
            style={{
              padding: "10px 12px",
              borderRadius: 8,
              textDecoration: "none",
              color: "var(--text)",
              background:
                location.pathname === item.path
                  ? "rgba(63,131,248,0.15)"
                  : "transparent",
            }}
          >
            {item.name}
          </Link>
        ))}
      </nav>
    </div>
  );
}
