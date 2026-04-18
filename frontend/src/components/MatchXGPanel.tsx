'use client';

import dynamic from 'next/dynamic';
import { useMemo } from 'react';
import { useTheme } from 'next-themes';
import { AlertTriangle, GaugeCircle, LineChart } from 'lucide-react';
import type { MatchXGLiveResponse, MatchXGPreMatchResponse } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

const ResponsiveLine = dynamic(
  () => import('@nivo/line').then((mod) => mod.ResponsiveLine),
  { ssr: false }
);

const ResponsiveBar = dynamic(
  () => import('@nivo/bar').then((mod) => mod.ResponsiveBar),
  { ssr: false }
);

interface MatchXGPanelProps {
  homeName: string;
  awayName: string;
  preMatch: MatchXGPreMatchResponse | null;
  live: MatchXGLiveResponse | null;
  loading?: boolean;
  error?: string | null;
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

function confidenceTone(label?: string): 'success' | 'warning' | 'danger' {
  const normalized = (label || '').toLowerCase();
  if (normalized === 'high') return 'success';
  if (normalized === 'medium') return 'warning';
  return 'danger';
}

export function MatchXGPanel({
  homeName,
  awayName,
  preMatch,
  live,
  loading = false,
  error = null,
}: MatchXGPanelProps) {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';
  const theme = useMemo(() => getNivoTheme(isDark), [isDark]);

  const model = live?.model || preMatch?.model || null;

  const trendPoints = useMemo(() => {
    if (live?.timeline?.length) {
      return live.timeline;
    }

    if (preMatch) {
      return [
        { minute: 0, home_xg: 0, away_xg: 0 },
        { minute: 45, home_xg: Number((preMatch.home.xg * 0.52).toFixed(3)), away_xg: Number((preMatch.away.xg * 0.52).toFixed(3)) },
        { minute: 90, home_xg: preMatch.home.xg, away_xg: preMatch.away.xg },
      ];
    }

    return [];
  }, [live, preMatch]);

  const currentHomeXg = live?.home_current_xg ?? preMatch?.home.xg ?? null;
  const currentAwayXg = live?.away_current_xg ?? preMatch?.away.xg ?? null;

  const lineData = [
    {
      id: homeName,
      data: trendPoints.map((point) => ({ x: `${point.minute}'`, y: point.home_xg })),
    },
    {
      id: awayName,
      data: trendPoints.map((point) => ({ x: `${point.minute}'`, y: point.away_xg })),
    },
  ];

  const comparisonData = [
    { team: homeName, xg: currentHomeXg ?? 0 },
    { team: awayName, xg: currentAwayXg ?? 0 },
  ];

  const disclaimers = useMemo(() => {
    const notes = [...(live?.disclaimers || []), ...(preMatch?.disclaimers || [])];
    return notes.filter((note, index) => note && notes.indexOf(note) === index);
  }, [live, preMatch]);

  if (loading && !preMatch && !live) {
    return (
      <Card className="mt-4">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-xl">
            <GaugeCircle className="h-5 w-5" />
            Expected Goals (xG)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="rounded-lg border border-dashed border-neutral-300 p-6 text-sm text-neutral-500 dark:border-neutral-700 dark:text-neutral-400">
            Loading xG forecast and live trend...
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error && !preMatch && !live) {
    return (
      <Card className="mt-4">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-xl">
            <GaugeCircle className="h-5 w-5" />
            Expected Goals (xG)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900/50 dark:bg-rose-900/20 dark:text-rose-200">
            {error}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!preMatch && !live) {
    return (
      <Card className="mt-4">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-xl">
            <GaugeCircle className="h-5 w-5" />
            Expected Goals (xG)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="rounded-lg border border-dashed border-neutral-300 p-6 text-sm text-neutral-500 dark:border-neutral-700 dark:text-neutral-400">
            xG data is not available yet for this match.
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="mt-4">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-xl">
          <GaugeCircle className="h-5 w-5" />
          Expected Goals (xG)
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Badge tone={model?.is_proxy ? 'warning' : 'success'}>
            {model?.is_proxy ? 'xG Proxy' : 'True xG'}
          </Badge>
          <Badge tone={confidenceTone(model?.confidence_label)}>
            {String(model?.confidence_label || 'low').toUpperCase()} CONFIDENCE
          </Badge>
          <Badge>{((model?.confidence_score || 0) * 100).toFixed(1)}%</Badge>
          {typeof live?.minute_context === 'number' ? <Badge>Minute {live.minute_context}</Badge> : null}
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <div className="rounded-lg border border-neutral-200 bg-neutral-50 p-3 dark:border-neutral-800 dark:bg-neutral-900">
            <p className="text-xs text-neutral-500 dark:text-neutral-400">{homeName}</p>
            <p className="text-2xl font-black text-sky-600 dark:text-sky-400">{(currentHomeXg ?? 0).toFixed(2)} xG</p>
          </div>
          <div className="rounded-lg border border-neutral-200 bg-neutral-50 p-3 dark:border-neutral-800 dark:bg-neutral-900">
            <p className="text-xs text-neutral-500 dark:text-neutral-400">{awayName}</p>
            <p className="text-2xl font-black text-amber-600 dark:text-amber-400">{(currentAwayXg ?? 0).toFixed(2)} xG</p>
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-xl border border-neutral-200 bg-white p-3 dark:border-neutral-800 dark:bg-neutral-950">
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-neutral-700 dark:text-neutral-200">
              <LineChart className="h-4 w-4" />
              xG Trend Over Time
            </div>
            <div className="h-[260px] w-full">
              <ResponsiveLine
                data={lineData}
                margin={{ top: 16, right: 16, bottom: 50, left: 48 }}
                theme={theme}
                xScale={{ type: 'point' }}
                yScale={{ type: 'linear', min: 0, max: 'auto' }}
                curve="monotoneX"
                lineWidth={3}
                colors={[isDark ? '#38bdf8' : '#0284c7', isDark ? '#fbbf24' : '#d97706']}
                pointSize={8}
                pointColor={{ theme: 'background' }}
                pointBorderWidth={2}
                pointBorderColor={{ from: 'serieColor' }}
                enableGridX={false}
                axisBottom={{ legend: 'Minute', legendOffset: 36, legendPosition: 'middle' }}
                axisLeft={{ legend: 'Cumulative xG', legendOffset: -38, legendPosition: 'middle' }}
                useMesh
                animate={false}
              />
            </div>
          </div>

          <div className="rounded-xl border border-neutral-200 bg-white p-3 dark:border-neutral-800 dark:bg-neutral-950">
            <div className="mb-2 text-sm font-semibold text-neutral-700 dark:text-neutral-200">Team xG Comparison</div>
            <div className="h-[260px] w-full">
              <ResponsiveBar
                data={comparisonData}
                keys={['xg']}
                indexBy="team"
                layout="horizontal"
                margin={{ top: 16, right: 16, bottom: 40, left: 90 }}
                theme={theme}
                colors={['#0ea5e9']}
                borderRadius={6}
                axisBottom={{ legend: 'xG', legendOffset: 32, legendPosition: 'middle' }}
                axisLeft={{ legend: '', legendOffset: 0, legendPosition: 'middle' }}
                labelSkipWidth={14}
                labelSkipHeight={14}
                labelTextColor="#0f172a"
                valueFormat={(value) => Number(value).toFixed(2)}
                animate={false}
              />
            </div>
          </div>
        </div>

        {disclaimers.length > 0 ? (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900 dark:border-amber-900/50 dark:bg-amber-900/20 dark:text-amber-100">
            <p className="mb-1 flex items-center gap-2 font-semibold">
              <AlertTriangle className="h-3.5 w-3.5" />
              Confidence and data quality notes
            </p>
            <ul className="list-disc space-y-1 pl-4">
              {disclaimers.map((note, index) => (
                <li key={`xg-note-${index}`}>{note}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
