import React, { useEffect, useState, ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import api from './api'; 
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend
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

interface DailyStat {
  date: string; // 예: "2025-08-01"
  total: number;
  avg_confidence: number;
  avg_freshness: number;
  variety: number;
}

// StatCard 컴포넌트의 props 타입을 정의
interface StatCardProps {
  title: string;
  value: string | number;
  change: string;
  icon: ReactNode; // 아이콘은 React 컴포넌트이므로 ReactNode 타입
}

// 변경률 계산 함수
const calculateChange = (current: number, previous: number, unit = ''): string => {
  if ((previous === 0 && current === 0) || current === previous) {
    return "변동 없음";
  }

  if (unit === "%") {
    if (previous === 0) {
      return current > 0 ? `+${current.toFixed(1)}%` : "변동 없음";
    }
    const percentage = ((current - previous) / previous) * 100;
    return `${percentage > 0 ? "+" : ""}${percentage.toFixed(1)}%`;
  }

  // ✅ 건/종류는 정수로
  const diff = current - previous;
  const isIntegerUnit = ["건", "종", "종류"].includes(unit);
  return `${diff > 0 ? "+" : ""}${isIntegerUnit ? Math.round(diff) : diff.toFixed(1)}${unit}`;
};

// StatCard 컴포넌트
const StatCard: React.FC<StatCardProps> = ({ title, value, change, icon }) => {
  const isChangeUp = change.startsWith("+");
  const isChangeDown = change.startsWith("-");
  const isPercent = change.includes("%");

  const colorClass = isChangeUp
    ? "text-green-500"
    : isChangeDown
    ? "text-red-500"
    : "text-gray-500";

  return (
    <div className="bg-white p-6 rounded-2xl shadow-md flex items-center justify-between">
      <div>
        <p className="text-sm font-medium text-gray-500">{title}</p>
        <p className="text-2xl font-bold text-gray-800">{value}</p>
        <p className={`text-sm mt-1 ${colorClass}`}>
          {change} {isPercent ? "(전날 대비)" : ""}
        </p>
      </div>
      <div className="bg-gray-800 text-white p-3 rounded-xl shadow-lg">
        {icon}
      </div>
    </div>
  );
};

const Dashboard = () => {
  const [summary, setSummary] = useState<SummaryData | null>(null);
  const [dailyStats, setDailyStats] = useState<DailyStat[]>([]);
  const [error, setError] = useState<string | null>(null);
  const location = useLocation();

  const fetchSummary = async () => {
    try {
      const res = await api.get("/stats/summary", {
        headers: { 'Cache-Control': 'no-cache' }
      });
      setSummary(res.data);
    } catch {
      setError("요약 데이터 로딩 실패");
    }
  };

  const fetchDailyStats = async () => {
    try {
      const res = await api.get<DailyStat[]>("/stats/daily", {
        headers: { 'Cache-Control': 'no-cache' }
      });
      setDailyStats(res.data);
    } catch {
      setError("일별 데이터 로딩 실패");
    }
  };

  // ✅ 최초 1회 호출
  useEffect(() => {
    fetchSummary();
    fetchDailyStats();
  }, []);

  // ✅ 쿼리 파라미터에 따라 강제 새로고침
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    if (params.get("refresh") === "true") {
      fetchSummary();
      fetchDailyStats();
    }
  }, [location.search]);

  // ✅ 자동 새로고침 (10초 간격)
  useEffect(() => {
    const interval = setInterval(() => {
      fetchSummary();
      fetchDailyStats();
    }, 10000); // 10초마다 자동 호출

    return () => clearInterval(interval);
  }, []);

  if (error) {
    return <div className="text-center p-8 bg-red-100 text-red-700 rounded-lg">{error}</div>;
  }

  if (!summary) {
    return <div className="text-center text-gray-500">대시보드 데이터를 불러오는 중...</div>;
  }

  const todayCount = summary.today;
  const yesterdayCount = summary.yesterday;

  const totalCount = summary.total;
  const totalBeforeToday = summary.total_before_today;

  const accuracyToday = summary.avg_confidence_today;
  const accuracyYesterday = summary.avg_confidence_yesterday;

  const freshnessToday = summary.avg_freshness_today;
  const freshnessYesterday = summary.avg_freshness_yesterday;

  const varietyCount = Object.keys(summary.ripeness_counts).filter(k => k !== "비디오분석").length;
  const varietyYesterday = summary.ripeness_types_yesterday;

  const COLORS: { [key: string]: string } = {
    "미숙": "#a3e635",
    "신선한 미숙": "#86efac",
    "완숙": "#fde047",
    "신선한 완숙": "#facc15",
    "과숙": "#f97316",
    "썩음": "#78350f",
  };
  const filteredRipeness = Object.entries(summary.ripeness_counts).filter(([k]) => k !== "비디오분석");
  const pieData = filteredRipeness.map(([k, v]) => ({ name: k, value: v }));
  const barData = filteredRipeness.map(([k, v]) => ({ name: k, count: v }));

  // 일별 종합 데이터
  const sortedStats = [...dailyStats].sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());

  // 퍼센트 라벨을 조각 안쪽에 표시하는 함수
  const renderCustomizedLabel = ({
    cx, cy, midAngle, innerRadius, outerRadius, percent,
  }: any) => {
    const RADIAN = Math.PI / 180;
    const radius = innerRadius + (outerRadius - innerRadius) * 0.5;
    const x = cx + radius * Math.cos(-midAngle * RADIAN);
    const y = cy + radius * Math.sin(-midAngle * RADIAN);

    return (
      <text x={x} y={y} fill="white" textAnchor="middle" dominantBaseline="central" fontSize={14}>
        {`${(percent * 100).toFixed(1)}%`}
      </text>
    );
  };
  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold text-brand-gray-900 mb-4 text-left md:text-left text-center">
        대시보드
      </h1>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <StatCard
            title="오늘 분석 건수"
            value={`${todayCount} 건`}
            change={calculateChange(todayCount, yesterdayCount, "건")} // 직접 계산
            icon={<MagnifyingGlassIcon className="h-6 w-6" />}
          />

          <StatCard
            title="총 분석 건수"
            value={`${totalCount} 건`}
            change={calculateChange(totalCount, totalBeforeToday, "건")}
            icon={<ChartBarIcon className="h-6 w-6" />}
          />

          <StatCard
            title="오늘 평균 정확도"
            value={`${accuracyToday.toFixed(1)} %`}
            change={calculateChange(accuracyToday, accuracyYesterday, "%")}  // ✅ 퍼센트 변화
            icon={<CheckCircleIcon className="h-6 w-6" />}
          />

          <StatCard
            title="오늘 평균 신선도"
            value={`${freshnessToday.toFixed(1)} %`}
            change={calculateChange(freshnessToday, freshnessYesterday, "%")}  // ✅ 퍼센트 변화
            icon={<BeakerIcon className="h-6 w-6" />}
          />

          <StatCard
            title="숙성 상태 다양성"
            value={`${varietyCount} 종류`}
            change={calculateChange(varietyCount, varietyYesterday, "종")}
            icon={<SparklesIcon className="h-6 w-6" />}
          />
        </div>

        <div className="bg-white p-6 rounded-2xl shadow-md w-full">
          <h3 className="text-lg font-bold text-gray-800 mb-4">🍌바나나 통계</h3>

          {barData.length > 0 && pieData.length > 0 ? (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              
              {/* 📈 Line Chart - 일별 분석 지표 추이 */}
              <div className="flex flex-col h-[300px]">
                <h4 className="text-md font-bold text-gray-800 mb-2 text-center lg:text-left">일별 분석 지표 추이</h4>
                <ResponsiveContainer width="100%" height={370}>
                  <LineChart data={sortedStats} margin={{ top: 40, right: 30, left: 10, bottom: 60 }}>
                    <XAxis dataKey="date" angle={-45} textAnchor="end" tick={{ fontSize: 12 }} height={60} />
                    <YAxis tick={{ fontSize: 12 }} />
                    <Tooltip 
                      formatter={(value: number, name: string) => {
                        if (name.includes("정확도") || name.includes("신선도")) {
                          return [`${value.toFixed(2)} %`, name];
                        }
                        return [value, name];
                      }}
                    />
                    <Legend verticalAlign="bottom" height={40} wrapperStyle={{ fontSize: 13 }} />
                    <Line type="monotone" dataKey="variety" name="다양성(종류 수)" stroke="#4B0082" strokeWidth={2} dot={{ r: 3 }} />
                    <Line type="monotone" dataKey="avg_freshness" name="신선도(%)" stroke="#FFA500" strokeWidth={2} dot={{ r: 3 }}/>
                    <Line type="monotone" dataKey="total" name="일별 분석 건수" stroke="#228B22" strokeWidth={2} dot={{ r: 3 }}/>
                    <Line type="monotone" dataKey="avg_confidence" name="정확도(%)" stroke="#008080" strokeWidth={2} dot={{ r: 3 }}/>
                  </LineChart>
                </ResponsiveContainer>
              </div>

              {/* 🥧 Pie Chart - 숙성도 비율 */}
              <div className="flex flex-col h-[300px]">
                <h4 className="text-md font-bold text-gray-800 mb-2 text-center lg:text-left">숙성도 비율</h4>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={pieData}
                      nameKey="name"
                      cx="50%"
                      cy="50%"  // 가운데 정렬
                      outerRadius={100}
                      labelLine={false}
                      label={renderCustomizedLabel}
                    >
                      {pieData.map(({ name }) => (
                        <Cell key={`cell-${name}`} fill={COLORS[name] || "#ccc"} />
                      ))}
                    </Pie>
                    <Tooltip />
                    <Legend verticalAlign="bottom" height={36} />
                  </PieChart>
                </ResponsiveContainer>
              </div>

            </div>
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