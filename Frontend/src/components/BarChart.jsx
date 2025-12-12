import { BarChart as BC, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

export default function BarChart({ data }) {
  return (
    <div style={{ width: "100%", height: 300 }}>
      <ResponsiveContainer>
        <BC data={data}>
          <XAxis dataKey="name" />
          <YAxis />
          <Tooltip />
          <Bar dataKey="minutes" fill="#4f8df7" radius={[6, 6, 0, 0]} />
        </BC>
      </ResponsiveContainer>
    </div>
  );
}
