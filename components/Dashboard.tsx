import React, { useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, LineChart, Line } from 'recharts';

// --- 타입 정의 ---
type AnalysisStats = {
  todayAnalyses: number;
  avgRipeness: number;
  totalUploads: number;
};

// --- 정적 데이터 (차트 및 목록용) ---
const weeklyAnalysisData = [
  { name: '월', analyses: 40 }, { name: '화', analyses: 30 }, { name: '수', analyses: 20 },
  { name: '목', analyses: 27 }, { name: '금', analyses: 18 }, { name: '토', analyses: 23 }, { name: '일', analyses: 34 },
];
const monthlyRipenessData = [
  { name: '1월', ripeness: 4.0 }, { name: '2월', ripeness: 3.0 }, { name: '3월', ripeness: 2.0 },
  { name: '4월', ripeness: 2.7 }, { name: '5월', ripeness: 1.8 }, { name: '6월', ripeness: 2.3 },
  { name: '7월', ripeness: 3.4 }, { name: '8월', ripeness: 4.2 }, { name: '9월', ripeness: 3.5 },
  { name: '10월', ripeness: 3.8 }, { name: '11월', ripeness: 3.9 }, { name: '12월', ripeness: 4.1 },
];
const projectsData = [
  { id: 1, name: '배치 A - 슈퍼마켓 납품', budget: '₩14,000,000', completion: 60, members: [1,2,3] },
  { id: 2, name: '배치 B - 지역 농장', budget: '₩3,000,000', completion: 10, members: [4,5] },
  { id: 3, name: '배치 C - 스무디 가게 재고', budget: '미설정', completion: 100, members: [1,5,6] },
  { id: 4, name: '배치 D - R&D 숙성도 연구', budget: '₩20,500,000', completion: 100, members: [1,2,4,6] },
  { id: 5, name: '배치 E - 유기농 인증', budget: '₩500,000', completion: 25, members: [3] },
  { id: 6, name: '배치 F - 새 센서 보정', budget: '₩2,000,000', completion: 40, members: [2, 5] },
];
const ordersData = [
  { icon: '💵', text: '₩2,400,000, 디자인 변경', time: '12월 22일 19:20', color: 'text-green-500' },
  { icon: '📦', text: '새 주문 #1832412', time: '12월 21일 23:00', color: 'text-red-500' },
  { icon: '💳', text: '4월 서버 비용 결제', time: '12월 21일 21:34', color: 'text-blue-500' },
  { icon: '✅', text: '주문 #4395133에 새 카드 추가', time: '12월 20일 02:20', color: 'text-orange-500' },
  { icon: '⚙️', text: '개발용 패키지 잠금 해제', time: '12월 18일 04:54', color: 'text-purple-500' },
  { icon: '📦', text: '새 주문 #9583120', time: '12월 17일', color: 'text-brand-gray-800' },
];

const StatCard: React.FC<{ title: string; value: string; change: string; icon: React.ReactNode; changeUp: boolean }> = ({ title, value, change, icon, changeUp }) => (
  <div className="bg-white p-6 rounded-2xl shadow-md flex items-center justify-between">
    <div>
      <p className="text-sm font-medium text-brand-gray-500">{title}</p>
      <p className="text-2xl font-bold text-brand-gray-800">{value}</p>
      <p className={`text-sm mt-1 ${changeUp ? 'text-green-500' : 'text-red-500'}`}>
        <span className="font-bold">{change}</span> 지난주보다
      </p>
    </div>
    <div className="bg-brand-gray-800 text-white p-3 rounded-xl shadow-lg">
      {icon}
    </div>
  </div>
);

const ChartCard: React.FC<{ title: string, subtitle: string, children: React.ReactNode }> = ({ title, subtitle, children }) => (
  <div className="bg-white p-6 rounded-2xl shadow-md">
    <div className="mb-6">
      <h3 className="text-lg font-bold text-brand-gray-800">{title}</h3>
      <p className="text-sm text-brand-gray-500">{subtitle}</p>
    </div>
    <div className="h-64">
      {children}
    </div>
  </div>
);

const ProgressBar: React.FC<{ percentage: number }> = ({ percentage }) => (
  <div className="w-full bg-brand-gray-200 rounded-full h-1.5">
    <div className="bg-brand-green h-1.5 rounded-full" style={{ width: `${percentage}%` }}></div>
  </div>
);

export default function Dashboard() {
  const [stats, setStats] = useState<AnalysisStats | null>(null);

  useEffect(() => {
    fetch("http://127.0.0.1:8000/stats")
      .then(res => res.json())
      .then(data => setStats(data))
      .catch(err => console.error("통계 불러오기 실패:", err));
  }, []);

  return (
    <div className="space-y-8">
      <h1 className="text-3xl font-bold text-brand-gray-900">대시보드</h1>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <StatCard title="오늘의 분석" value={stats ? `${stats.todayAnalyses} 건` : '로딩 중...'} change="+55%" icon={<svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>} changeUp={true} />
        <StatCard title="평균 숙성도" value={stats ? `${stats.avgRipeness.toFixed(1)} 점` : '로딩 중...'} change="+3%" icon={<svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.085a2 2 0 00-1.736.97l-2.096 4.192M14 10l-2 4m0 0l-2-4m2 4v4" /></svg>} changeUp={true} />
        <StatCard title="총 업로드" value={stats ? `${stats.totalUploads.toLocaleString()} 건` : '로딩 중...'} change="+5%" icon={<svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>} changeUp={true} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1">
          <ChartCard title="주간 분석" subtitle="지난 캠페인 성과">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={weeklyAnalysisData} margin={{ top: 5, right: 20, left: -10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" axisLine={false} tickLine={false} />
                <YAxis axisLine={false} tickLine={false} />
                <Tooltip wrapperClassName="rounded-md shadow-lg" />
                <Bar dataKey="analyses" name="분석 수" fill="#4CAF50" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>
        <div className="lg:col-span-2">
          <ChartCard title="월간 평균 숙성도" subtitle="(+15%) 오늘의 매출 증가">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={monthlyRipenessData} margin={{ top: 5, right: 20, left: -10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" axisLine={false} tickLine={false} />
                <YAxis axisLine={false} tickLine={false} />
                <Tooltip wrapperClassName="rounded-md shadow-lg" />
                <Legend />
                <Line type="monotone" dataKey="ripeness" name="평균 숙성도" stroke="#4CAF50" strokeWidth={2} dot={{ r: 4 }} activeDot={{ r: 8 }} />
              </LineChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* 분석 배치 및 주문 개요는 생략하거나 유지 */}
      </div>
    </div>
  );
}