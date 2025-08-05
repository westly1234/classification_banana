import React, { useEffect, useState, ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import api from './api';
import {
    ComposedChart, Area, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend, Label
} from 'recharts';
import { ChartBarIcon, MagnifyingGlassIcon, SparklesIcon, CheckCircleIcon, BeakerIcon, ArrowUpIcon, ArrowDownIcon } from '@heroicons/react/24/solid';

// --- 백엔드 API 응답 인터페이스 (원본 유지) ---
interface SummaryData {
    today: number; yesterday: number; total: number; total_before_today: number;
    ripeness_counts: { [key: string]: number };
    ripeness_types_yesterday: number; avg_confidence_today: number; avg_confidence_yesterday: number;
    avg_freshness_today: number; avg_freshness_yesterday: number;
}
interface DailyStat {
    date: string; total: number; avg_confidence: number; avg_freshness: number; variety: number;
}
interface StatCardProps {
    title: string; value: string; change: string; icon: ReactNode;
}

// --- 헬퍼 함수 (원본 유지) ---
const calculateChange = (current: number, previous: number, unit = ''): string => {
    if ((previous === 0 && current === 0) || current === previous) return "변동 없음";
    if (unit === "%") {
        if (previous === 0) return current > 0 ? `+${current.toFixed(1)}%` : "변동 없음";
        const percentage = ((current - previous) / previous) * 100;
        return `${percentage > 0 ? "+" : ""}${percentage.toFixed(1)}%`;
    }
    const diff = current - previous;
    const isIntegerUnit = ["건", "종", "종류"].includes(unit);
    return `${diff > 0 ? "+" : ""}${isIntegerUnit ? Math.round(diff) : diff.toFixed(1)}${unit}`;
};

// --- 여기부터 JSX 및 디자인 전면 교체 ---

const StatCard: React.FC<StatCardProps> = ({ title, value, change, icon }) => {
    const isChangeUp = change.startsWith("+");
    const isChangeDown = change.startsWith("-");
    const colorClasses = {
        iconContainer: isChangeUp ? "bg-emerald-100" : isChangeDown ? "bg-rose-100" : "bg-slate-100",
        icon: isChangeUp ? "text-emerald-600" : isChangeDown ? "text-rose-600" : "text-slate-600",
        text: isChangeUp ? "text-emerald-500" : isChangeDown ? "text-rose-500" : "text-slate-500",
    };
    return (
        <div className="bg-white p-6 rounded-2xl shadow-lg transition-all duration-300 hover:shadow-xl hover:-translate-y-1">
            <div className="flex items-start justify-between">
                <div className={`p-3 rounded-lg ${colorClasses.iconContainer}`}>
                    {React.cloneElement(icon as React.ReactElement, { className: `h-7 w-7 ${colorClasses.icon}` })}
                </div>
                <div className={`flex items-center gap-1 text-sm font-bold ${colorClasses.text}`}>
                    {isChangeUp && <ArrowUpIcon className="h-4 w-4" />}
                    {isChangeDown && <ArrowDownIcon className="h-4 w-4" />}
                    <span>{change}</span>
                </div>
            </div>
            <div className="mt-4">
                <p className="text-3xl font-bold text-slate-800">{value}</p>
                <p className="text-sm font-medium text-slate-500 mt-1">{title}</p>
            </div>
        </div>
    );
};

const ChartContainer: React.FC<{ title: string; children: ReactNode }> = ({ title, children }) => (
    <div className="bg-white p-6 rounded-2xl shadow-lg h-full">
        <h3 className="text-xl font-bold text-slate-800 mb-6">{title}</h3>
        <div className="h-[400px]">
            {children}
        </div>
    </div>
);

const CustomTooltip: React.FC<any> = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
        return (
            <div className="bg-white/70 backdrop-blur-sm p-4 rounded-xl shadow-lg border border-slate-200">
                <p className="font-bold text-slate-700">{label}</p>
                {payload.map((entry: any, index: number) => (
                    <p key={`item-${index}`} style={{ color: entry.stroke || entry.payload.fill }} className="text-sm font-medium">
                        {`${entry.name}: ${entry.value.toFixed(1)} ${entry.name.includes('%') ? '%' : (entry.name.includes('종') ? '종' : '건')}`}
                    </p>
                ))}
            </div>
        );
    }
    return null;
};

const renderCustomizedLabel = ({ cx, cy, midAngle, innerRadius, outerRadius, percent }: any) => {
    if (percent < 0.05) return null; // 5% 미만 라벨은 숨겨서 깔끔하게
    const RADIAN = Math.PI / 180;
    const radius = innerRadius + (outerRadius - innerRadius) * 0.5;
    const x = cx + radius * Math.cos(-midAngle * RADIAN);
    const y = cy + radius * Math.sin(-midAngle * RADIAN);
    return (
      <text x={x} y={y} fill="white" textAnchor="middle" dominantBaseline="central" className="text-sm font-bold drop-shadow-md">
        {`${(percent * 100).toFixed(0)}%`}
      </text>
    );
};

const Dashboard = () => {
    const [summary, setSummary] = useState<SummaryData | null>(null);
    const [dailyStats, setDailyStats] = useState<DailyStat[]>([]);
    const [error, setError] = useState<string | null>(null);
    const location = useLocation();

    const fetchData = async () => {
        try {
            const [summaryRes, dailyRes] = await Promise.all([
                api.get("/stats/summary", { headers: { 'Cache-Control': 'no-cache' }}),
                api.get<DailyStat[]>("/stats/daily", { headers: { 'Cache-Control': 'no-cache' }})
            ]);
            setSummary(summaryRes.data);
            setDailyStats(dailyRes.data);
        } catch (err) { setError("대시보드 데이터를 불러오는 데 실패했습니다. 잠시 후 다시 시도해주세요."); }
    };

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 10000);
        return () => clearInterval(interval);
    }, []);

    useEffect(() => {
        if (new URLSearchParams(location.search).get("refresh") === "true") fetchData();
    }, [location.search]);

    if (error) return <div className="text-center p-8 bg-rose-100 text-rose-700 rounded-lg">{error}</div>;
    if (!summary) return <div className="w-full h-screen flex items-center justify-center text-slate-500 text-lg">대시보드 데이터를 불러오는 중...</div>;

    const { today, yesterday, total, total_before_today, avg_confidence_today, avg_confidence_yesterday, avg_freshness_today, avg_freshness_yesterday, ripeness_counts, ripeness_types_yesterday } = summary;
    const varietyToday = Object.keys(ripeness_counts).filter(k => k !== "비디오분석").length;

    const COLORS: { [key: string]: string } = { "미숙": "#facc15", "신선한 미숙": "#a3e635", "완숙": "#4ade80", "신선한 완숙": "#22c55e", "과숙": "#f97316", "썩음": "#78350f" };
    const pieData = Object.entries(ripeness_counts).filter(([k]) => k !== "비디오분석").map(([name, value]) => ({ name, value }));
    const sortedDailyStats = [...dailyStats].sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());

    return (
        <div className="bg-slate-50 min-h-screen p-4 sm:p-6 lg:p-8">
            <div className="max-w-screen-2xl mx-auto">
                <header className="mb-8">
                    <h1 className="text-4xl font-extrabold text-slate-900 tracking-tight">분석 대시보드</h1>
                    <p className="mt-2 text-lg text-slate-600">실시간 바나나 숙성도 분석 현황을 확인하세요.</p>
                </header>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-6 mb-8">
                    <StatCard title="오늘 분석 건수" value={`${today} 건`} change={calculateChange(today, yesterday, "건")} icon={<MagnifyingGlassIcon />} />
                    <StatCard title="오늘 평균 정확도" value={`${avg_confidence_today.toFixed(1)}%`} change={calculateChange(avg_confidence_today, avg_confidence_yesterday, "%")} icon={<CheckCircleIcon />} />
                    <StatCard title="오늘 평균 신선도" value={`${avg_freshness_today.toFixed(1)}%`} change={calculateChange(avg_freshness_today, avg_freshness_yesterday, "%")} icon={<BeakerIcon />} />
                    <StatCard title="숙성 상태 다양성" value={`${varietyToday} 종`} change={calculateChange(varietyToday, ripeness_types_yesterday, "종")} icon={<SparklesIcon />} />
                    <StatCard title="총 누적 분석" value={total.toLocaleString('ko-KR')} change={calculateChange(total, total_before_today, "건")} icon={<ChartBarIcon />} />
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-5 gap-8">
                    <div className="lg:col-span-3">
                        <ChartContainer title="일별 분석 트렌드">
                            <ResponsiveContainer width="100%" height="100%">
                                <ComposedChart data={sortedDailyStats} margin={{ top: 5, right: 20, left: -10, bottom: 5 }}>
                                    <defs>
                                        <linearGradient id="colorTotal" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#6366f1" stopOpacity={0.7}/><stop offset="95%" stopColor="#6366f1" stopOpacity={0}/></linearGradient>
                                    </defs>
                                    <XAxis dataKey="date" tick={{ fontSize: 12, fill: '#64748b' }} tickLine={false} axisLine={false} />
                                    <YAxis yAxisId="left" tick={{ fontSize: 12, fill: '#64748b' }} tickLine={false} axisLine={false} />
                                    <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 12, fill: '#64748b' }} tickLine={false} axisLine={false} />
                                    <Tooltip content={<CustomTooltip />} />
                                    <Legend verticalAlign="top" align="right" height={40} iconType="circle" />
                                    <Area type="monotone" yAxisId="left" dataKey="total" name="분석 건수" stroke="#6366f1" strokeWidth={3} fillOpacity={1} fill="url(#colorTotal)" />
                                    <Line type="monotone" yAxisId="right" dataKey="avg_freshness" name="신선도(%)" stroke="#f59e0b" strokeWidth={2.5} dot={false} />
                                    <Line type="monotone" yAxisId="right" dataKey="avg_confidence" name="정확도(%)" stroke="#ec4899" strokeWidth={2.5} dot={false} />
                                    <Line type="monotone" yAxisId="left" dataKey="variety" name="다양성(종)" stroke="#14b8a6" strokeWidth={2.5} strokeDasharray="5 5" dot={false} />
                                </ComposedChart>
                            </ResponsiveContainer>
                        </ChartContainer>
                    </div>

                    <div className="lg:col-span-2">
                        <ChartContainer title="오늘의 숙성도 분포">
                            {pieData.length > 0 ? (
                                <ResponsiveContainer width="100%" height="100%">
                                    <PieChart>
                                        <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius="60%" outerRadius="85%" fill="#8884d8" paddingAngle={5} labelLine={false} label={renderCustomizedLabel}>
                                            {pieData.map((entry, index) => (
                                                <Cell key={`cell-${index}`} fill={COLORS[entry.name] || '#ccc'} stroke="none" />
                                            ))}
                                            <Label value={today} position="center" className="text-4xl font-bold fill-slate-700" dy={-5} />
                                            <Label value="오늘 분석 건" position="center" dy={20} className="text-sm fill-slate-500" />
                                        </Pie>
                                        <Tooltip formatter={(value: number, name: string) => [`${value}건`, name]}/>
                                        <Legend iconType="circle" />
                                    </PieChart>
                                </ResponsiveContainer>
                            ) : (
                                <div className="flex items-center justify-center h-full text-slate-500">오늘 분석 데이터가 없습니다.</div>
                            )}
                        </ChartContainer>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default Dashboard;