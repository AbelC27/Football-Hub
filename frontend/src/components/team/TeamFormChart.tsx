'use client';

import dynamic from 'next/dynamic';
import { useMemo } from 'react';
import { useTheme } from 'next-themes';
import type { TeamFormWindowMetrics } from '@/lib/api';

const ResponsiveLine = dynamic(
  () => import('@nivo/line').then((mod) => mod.ResponsiveLine),
  { ssr: false }
);

const ResponsiveBar = dynamic(
  () => import('@nivo/bar').then((mod) => mod.ResponsiveBar),
  { ssr: false }
);

export type TeamFormChartType = 'trend' | 'results' | 'split';

interface TeamFormChartProps {
  metrics: TeamFormWindowMetrics;
  chartType: TeamFormChartType;
}

function getNivoTheme(isDark: boolean) {
  const axisColor = isDark ? '#d4d4d8' : '#3f3f46';
  const gridColor = isDark ? '#27272a' : '#e4e4e7';

  return {
    text: {
      fill: axisColor,
      fontSize: 12,
    },
    axis: {
      ticks: {
        line: { stroke: gridColor, strokeWidth: 1 },
        text: { fill: axisColor, fontSize: 11 },
      },
      legend: {
        text: { fill: axisColor, fontSize: 12 },
      },
    },
    grid: {
      line: {
        stroke: gridColor,
        strokeWidth: 1,
      },
    },
    tooltip: {
      container: {
        background: isDark ? '#111827' : '#ffffff',
        color: isDark ? '#f5f5f5' : '#111827',
        borderRadius: '8px',
        fontSize: '12px',
        boxShadow: '0 8px 26px rgba(0,0,0,0.18)',
      },
    },
  };
}

function resultClass(result: string) {
  if (result === 'W') return 'bg-emerald-500/20 text-emerald-700 dark:text-emerald-300';
  if (result === 'D') return 'bg-amber-500/20 text-amber-700 dark:text-amber-300';
  return 'bg-rose-500/20 text-rose-700 dark:text-rose-300';
}

export function TeamFormChart({ metrics, chartType }: TeamFormChartProps) {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';

  const theme = useMemo(() => getNivoTheme(isDark), [isDark]);

  if (metrics.matches_count === 0) {
    return (
      <div className="rounded-xl border border-dashed border-neutral-300 bg-neutral-50 p-6 text-sm text-neutral-600 dark:border-neutral-700 dark:bg-neutral-900/70 dark:text-neutral-300">
        No finished matches are available in the selected scope yet.
      </div>
    );
  }

  const cumulativeTrend = [
    {
      id: 'Cumulative Points',
      data: metrics.points_trend.map((entry) => ({
        x: entry.label,
        y: entry.cumulative_points,
        result: entry.result,
      })),
    },
  ];

  const resultBars = [
    { result: 'Wins', count: metrics.result_distribution.W },
    { result: 'Draws', count: metrics.result_distribution.D },
    { result: 'Losses', count: metrics.result_distribution.L },
  ];

  const splitBars = [
    {
      split: 'Home',
      Points: metrics.home_away_split.home.points,
      'Goals For': metrics.home_away_split.home.goals_for,
      'Goals Against': metrics.home_away_split.home.goals_against,
    },
    {
      split: 'Away',
      Points: metrics.home_away_split.away.points,
      'Goals For': metrics.home_away_split.away.goals_for,
      'Goals Against': metrics.home_away_split.away.goals_against,
    },
  ];

  return (
    <div className="space-y-4">
      <div className="h-[300px] w-full md:h-[360px]">
        {chartType === 'trend' && (
          <ResponsiveLine
            data={cumulativeTrend}
            margin={{ top: 24, right: 20, bottom: 52, left: 48 }}
            theme={theme}
            xScale={{ type: 'point' }}
            yScale={{ type: 'linear', min: 0, max: 'auto' }}
            curve="monotoneX"
            lineWidth={3}
            colors={[isDark ? '#22d3ee' : '#0284c7']}
            pointSize={9}
            pointColor={{ theme: 'background' }}
            pointBorderWidth={2}
            pointBorderColor={{ from: 'serieColor' }}
            enableArea
            areaOpacity={0.15}
            enableGridX={false}
            axisBottom={{ legend: 'Most recent window sequence', legendOffset: 38, legendPosition: 'middle' }}
            axisLeft={{ legend: 'Cumulative points', legendOffset: -38, legendPosition: 'middle' }}
            useMesh
            enableSlices="x"
          />
        )}

        {chartType === 'results' && (
          <ResponsiveBar
            data={resultBars}
            keys={['count']}
            indexBy="result"
            margin={{ top: 20, right: 20, bottom: 48, left: 48 }}
            theme={theme}
            padding={0.35}
            colors={({ data }) => {
              if (data.result === 'Wins') return '#10b981';
              if (data.result === 'Draws') return '#f59e0b';
              return '#f43f5e';
            }}
            borderRadius={6}
            axisBottom={{ legend: 'Result', legendOffset: 36, legendPosition: 'middle' }}
            axisLeft={{ legend: 'Matches', legendOffset: -36, legendPosition: 'middle' }}
            labelSkipWidth={14}
            labelSkipHeight={14}
            labelTextColor="#0f172a"
            animate={false}
          />
        )}

        {chartType === 'split' && (
          <ResponsiveBar
            data={splitBars}
            keys={['Points', 'Goals For', 'Goals Against']}
            indexBy="split"
            margin={{ top: 20, right: 20, bottom: 48, left: 50 }}
            theme={theme}
            padding={0.26}
            groupMode="grouped"
            colors={['#0ea5e9', '#22c55e', '#fb7185']}
            borderRadius={6}
            axisBottom={{ legend: 'Venue split', legendOffset: 36, legendPosition: 'middle' }}
            axisLeft={{ legend: 'Count', legendOffset: -36, legendPosition: 'middle' }}
            labelSkipWidth={14}
            labelSkipHeight={14}
            animate={false}
          />
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        {metrics.form.map((result, idx) => (
          <span
            key={`${result}-${idx}`}
            className={`inline-flex min-w-9 items-center justify-center rounded-md px-2 py-1 text-xs font-semibold ${resultClass(result)}`}
          >
            {result}
          </span>
        ))}
      </div>
    </div>
  );
}
