export default function StatCard({ title, value }) {
  return (
    <div style={{
      background: "white",
      padding: "20px",
      borderRadius: "10px",
      flex: 1,
      marginRight: "15px",
      boxShadow: "0 2px 6px rgba(0,0,0,0.1)"
    }}>
      <div style={{ fontSize: "16px", color: "#666" }}>{title}</div>
      <div style={{ fontSize: "28px", fontWeight: "bold", marginTop: "10px" }}>
        {value}
      </div>
    </div>
  );
}
