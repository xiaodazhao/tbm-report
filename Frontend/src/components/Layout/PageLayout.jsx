export default function PageLayout({ children }) {
  return (
    <div
      style={{
        marginLeft: 260,       // 给侧边栏让出空间
        padding: "40px",
        minHeight: "100vh",
        background: "var(--bg)",
        color: "var(--text)",
        transition: "0.3s",
      }}
    >
      {children}
    </div>
  );
}
