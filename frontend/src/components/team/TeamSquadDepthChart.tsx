'use client';

import dynamic from 'next/dynamic';
import { useMemo } from 'react';
import { useTheme } from 'next-themes';
import type { TeamSquadDepthPositionMetrics } from '@/lib/api';

const ResponsiveBar = dynamic(
  () => import('@nivo/bar').then((mod) => mod.ResponsiveBar),
  { ssr: false }
);

export type SquadDepthChartType = 'quality' | 'availability';

interface TeamSquadDepthChartProps {
  positions: TeamSquadDepthPositionMetrics[];
  chartType: SquadDepthChartType;
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

function shortPositionLabel(label: string) {
  if (label === 'Goalkeeper') return 'GK';
  if (label === 'Defender') return 'DEF';
  if (label === 'Midfielder') return 'MID';
  if (label === 'Attacker') return 'ATT';
  return 'OTH';
}

export function TeamSquadDepthChart({ positions, chartType }: TeamSquadDepthChartProps) {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';

  const theme = useMemo(() => getNivoTheme(isDark), [isDark]);

  const chartData = positions.map((position) => ({
    position: shortPositionLabel(position.position_label),
    Starter: position.starter_quality ?? 0,
    Bench: position.bench_quality ?? 0,
    Availability: position.availability_pct ?? 0,
    squadCount: position.squad_count,
    starterCount: position.starter_count,
    benchCount: position.bench_count,
    hasQuality: position.quality_data_points > 0,
    hasAvailability: position.availability_data_points > 0,
  }));

  const hasQuality = positions.some((position) => position.quality_data_points > 0);
  const hasAvailability = positions.some((position) => position.availability_data_points > 0);

  if (positions.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-neutral-300 bg-neutral-50 p-6 text-sm text-neutral-600 dark:border-neutral-700 dark:bg-neutral-900/70 dark:text-neutral-300">
        Squad depth cannot be rendered because no squad data was returned.
      </div>
    );
  }

  if (chartType === 'quality' && !hasQuality) {
    return (
      <div className="rounded-xl border border-dashed border-neutral-300 bg-neutral-50 p-6 text-sm text-neutral-600 dark:border-neutral-700 dark:bg-neutral-900/70 dark:text-neutral-300">
        Starter and bench quality need rating or season-stat inputs, which are currently missing.
      </div>
    );
  }

  if (chartType === 'availability' && !hasAvailability) {
    return (
      <div className="rounded-xl border border-dashed border-neutral-300 bg-neutral-50 p-6 text-sm text-neutral-600 dark:border-neutral-700 dark:bg-neutral-900/70 dark:text-neutral-300">
        Availability metrics are missing because minutes-played data is incomplete.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="h-[300px] w-full md:h-[360px]">
        {chartType === 'quality' && (
          <ResponsiveBar
            data={chartData}
            keys={['Starter', 'Bench']}
            indexBy="position"
            margin={{ top: 20, right: 22, bottom: 48, left: 52 }}
            theme={theme}
            padding={0.28}
            groupMode="grouped"
            colors={['#0ea5e9', '#a78bfa']}
            borderRadius={6}
            axisBottom={{ legend: 'Position', legendOffset: 36, legendPosition: 'middle' }}
            axisLeft={{ legend: 'Quality score', legendOffset: -38, legendPosition: 'middle' }}
            minValue={0}
            maxValue={100}
            labelSkipWidth={14}
            labelSkipHeight={14}
            animate={false}
          />
        )}

        {chartType === 'availability' && (
          <ResponsiveBar
            data={chartData}
            keys={['Availability']}
            indexBy="position"
            margin={{ top: 20, right: 20, bottom: 48, left: 52 }}
            theme={theme}
            padding={0.32}
            colors={['#10b981']}
            borderRadius={6}
            axisBottom={{ legend: 'Position', legendOffset: 36, legendPosition: 'middle' }}
            axisLeft={{ legend: 'Availability %', legendOffset: -38, legendPosition: 'middle' }}
            minValue={0}
            maxValue={100}
            labelSkipWidth={14}
            labelSkipHeight={14}
            animate={false}
          />
        )}
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs text-neutral-600 dark:text-neutral-300 sm:grid-cols-4">
        {positions.map((position) => (
          <div
            key={position.position_key}
            className="rounded-md border border-neutral-200 bg-white p-2 dark:border-neutral-800 dark:bg-neutral-900"
          >
            <div className="font-semibold">{shortPositionLabel(position.position_label)}</div>
            <div>Squad: {position.squad_count}</div>
            <div>XI: {position.starter_count}</div>
            <div>Bench: {position.bench_count}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
