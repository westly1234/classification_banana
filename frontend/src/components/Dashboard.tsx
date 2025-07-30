// ✅ 현실 기반 대시보드 (분석 데이터 연동)
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line
} from 'recharts';

const StatCard = ({ title, value, change, icon, changeUp }) => (
  <div className="bg-white p-6 rounded-2xl shadow-md flex items-center justify-between">
    <div>
      <p className="text-sm font-medium text-brand-gray-500">{title}</p>
      <p className="text-2xl font-bold text-brand-gray-800">{value}</p>
      <p className={`text-sm mt-1 ${changeUp ? 'text-green-500' : 'text-red-500'}`}>{change}</p>
    </div>
    <div className="bg-brand-gray-800 text-white p-3 rounded-xl shadow-lg">{icon}</div>
  </div>
);

const Dashboard = () => {
  const [summary, setSummary] = useState(null);

  useEffect(() => {
    axios.get("http://localhost:8000/stats/summary")
      .then(res => setSummary(res.data))
      .catch(err => console.error("API 오류", err));
  }, []);

  return (
    <div className="space-y-8">
      <h1 className="text-3xl font-bold text-brand-gray-900">대시보드</h1>

      {summary && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <StatCard
            title="오늘 분석"
            value={`${summary.today} 건`}
            change="+10%"
            icon={<span>🔍</span>}
            changeUp={true}
          />
          <StatCard
            title="총 분석 건수"
            value={`${summary.total} 건`}
            change="+5%"
            icon={<span>📊</span>}
            changeUp={true}
          />
          <StatCard
            title="숙성 상태 다양성"
            value={`${Object.keys(summary.ripeness_counts).length}종류`}
            change="+1종"
            icon={<span>🍌</span>}
            changeUp={true}
          />
        </div>
      )}

      {summary && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white p-6 rounded-2xl shadow-md">
            <h3 className="text-lg font-bold text-brand-gray-800 mb-4">숙성도 분포</h3>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart
                data={Object.entries(summary.ripeness_counts).map(([k, v]) => ({ ripeness: k, count: v }))}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="ripeness" />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="count" fill="#4CAF50" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
};

export default Dashboard;
