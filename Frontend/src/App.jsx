import { Suspense, lazy } from "react";

const Dashboard = lazy(() => import("@/features/dashboard/Dashboard"));

function App() {
  return (
    <Suspense fallback={<AppLoading />}>
      <Dashboard />
    </Suspense>
  );
}

export default App;

function AppLoading() {
  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "linear-gradient(135deg, #ecfeff 0%, #f8fafc 100%)",
        color: "#0f172a",
        fontSize: 18,
        fontWeight: 800,
      }}
    >
      正在加载 TBM 分析驾驶舱...
    </div>
  );
}
