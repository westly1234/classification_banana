import React, { useEffect, useState, ReactNode } from 'react';
import api from './api'; 

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { ChartBarIcon, MagnifyingGlassIcon, SparklesIcon, CheckCircleIcon, BeakerIcon } from '@heroicons/react/24/outline';

//백엔드 API 응답의 모양을 정의하는 인터페이스
interface SummaryData {
  today: number;
  yesterday: number;
  total: number;
  total_before_today: number;
  ripeness_counts: { [key: string]: number }; // { "완숙": 5, "과숙": 4 } 와 같은 형태
  ripeness_types_yesterday: number;
  avg_confidence_today: number;
  avg_confidence_yesterday: number;
  avg_freshness_today: number;
  avg_freshness_yesterday: number;
}

// StatCard 컴포넌트의 props 타입을 정의
interface StatCardProps {
  title: string;
  value: string;
  change: string;
  icon: ReactNode; // 아이콘은 React 컴포넌트이므로 ReactNode 타입
}

// 함수 매개변수에 타입을 명시
const calculateChange = (current: number, previous: number, unit = ''): string => {
    if ((previous === 0 && current === 0) || current === previous) {
        return "변동 없음";
    }
    if (previous === 0) {
        return current > 0 ? `+${current}${unit}` : "변동 없음";
    }
    const percentage = ((current - previous) / previous) * 100;
    if (percentage > 0) {
        return `+${percentage.toFixed(1)}%`;
    } else if (percentage < 0) {
        return `${percentage.toFixed(1)}%`;
    }
    return "변동 없음";
};

// 컴포넌트 props에 타입을 적용 (React.FC 사용)
const StatCard: React.FC<StatCardProps> = ({ title, value, change, icon }) => {
    const isChangeUp = change.startsWith('+');
    const isChangeDown = change.startsWith('-');
    
    return (
        <div className="bg-white p-6 rounded-2xl shadow-md flex items-center justify-between">
            <div>
                <p className="text-sm font-medium text-gray-500">{title}</p>
                <p className="text-2xl font-bold text-gray-800">{value}</p>
                <p className={`text-sm mt-1 ${isChangeUp ? 'text-green-500' : isChangeDown ? 'text-red-500' : 'text-gray-500'}`}>
                    {change} (어제 대비)
                </p>
            </div>
            <div className="bg-gray-800 text-white p-3 rounded-xl shadow-lg">
                {icon}
            </div>
        </div>
    );
};

const Dashboard = () => {
  // useState에 API 데이터의 타입(SummaryData)을 명시
  const [summary, setSummary] = useState<SummaryData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchSummary = () => {
        api.get<SummaryData>("/stats/summary")
           .then(res => setSummary(res.data))
           .catch(() => setError("데이터 불러오기 실패"));
    };
      fetchSummary();

      const interval = setInterval(fetchSummary, 5000);
      return () => clearInterval(interval);
  }, []);
  
  if (error) {
      return <div className="text-center p-8 bg-red-100 text-red-700 rounded-lg">{error}</div>;
  }
  
  // summary가 null이 아님을 TypeScript에게 확실히 알려준 후 사용
  if (!summary) {
      return <div className="text-center text-gray-500">대시보드 데이터를 불러오는 중...</div>;
  }

  const todayChange = calculateChange(summary.today, summary.yesterday);
  const totalChange = calculateChange(summary.total, summary.total_before_today);
  const varietyCount = Object.keys(summary.ripeness_counts).length;
  const varietyChangeText = calculateChange(varietyCount, summary.ripeness_types_yesterday, '종');
  const accuracyChange = calculateChange(
      summary.avg_confidence_today,
      summary.avg_confidence_yesterday,
      '%'
  );
  const freshnessChange = calculateChange(
      summary.avg_freshness_today,
      summary.avg_freshness_yesterday,
      '%'
  );

  return (
    <div className="space-y-8">
      <h1 className="text-3xl font-bold text-gray-900">대시보드</h1>

        <div className="grid grid-cols-1 md-grid-cols-2 lg-grid-cols-3 gap-6">
          <StatCard
            title="오늘 분석 건수"
            value={`${summary.today} 건`}
            change={todayChange}
            icon={<MagnifyingGlassIcon className="h-6 w-6" />}
          />
          <StatCard
            title="총 분석 건수"
            value={`${summary.total} 건`}
            change={totalChange}
            icon={<ChartBarIcon className="h-6 w-6" />}
          />
          <StatCard
            title="오늘 평균 정확도"
            value={`${summary.avg_confidence_today.toFixed(1)} %`}
            change={accuracyChange}
            icon={<CheckCircleIcon className="h-6 w-6" />}
          />
          <StatCard
              title="오늘 평균 신선도"
              value={`${summary.avg_freshness_today.toFixed(1)} %`}
              change={freshnessChange}
              icon={<BeakerIcon className="h-6 w-6" />}
          />
          <StatCard
            title="숙성 상태 다양성"
            value={`${varietyCount} 종류`}
            change={varietyChangeText}
            icon={<SparklesIcon className="h-6 w-6" />}
          />
        </div>

        <div className="bg-white p-6 rounded-2xl shadow-md">
            <h3 className="text-lg font-bold text-gray-800 mb-4">숙성도 분포</h3>
            {Object.keys(summary.ripeness_counts).length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={Object.entries(summary.ripeness_counts).map(([k, v]) => ({ name: k, count: v }))}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} />
                        <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                        <YAxis allowDecimals={false} />
                        <Tooltip />
                        <Bar dataKey="count" fill="#FFC107" radius={[4, 4, 0, 0]} />
                    </BarChart>
                </ResponsiveContainer>
            ) : (
                <div className="flex items-center justify-center h-[300px] text-gray-500">
                    분석 데이터가 없습니다.
                </div>
            )}
        </div>
    </div>
  );
};

export default Dashboard;