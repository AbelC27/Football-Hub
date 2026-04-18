'use client';

import dynamic from 'next/dynamic';
import { ComparedPlayer } from '@/lib/api';

const ResponsiveRadar = dynamic(
  () => import('@nivo/radar').then((mod) => mod.ResponsiveRadar),
  { ssr: false }
);

interface PlayerComparisonRadarProps {
  player1: ComparedPlayer;
  player2: ComparedPlayer;
}

interface MetricConfig {
  key: string;
  label: string;
  max: number;
  getter: (player: ComparedPlayer) => number | null | undefined;
}

const METRICS: MetricConfig[] = [
  {
    key: 'rating',
    label: 'Rating',
    max: 10,
    getter: (player) => player.stats?.rating,
  },
  {
    key: 'goals',
    label: 'Goals',
    max: 20,
    getter: (player) => player.stats?.goals,
  },
  {
    key: 'assists',
    label: 'Assists',
    max: 12,
    getter: (player) => player.stats?.assists,
  },
  {
    key: 'minutes',
    label: 'Minutes',
    max: 3000,
    getter: (player) => player.stats?.minutes,
  },
  {
    key: 'discipline',
    label: 'Discipline',
    max: 1,
    getter: (player) => {
      const yellow = player.stats?.yellow_cards;
      const red = player.stats?.red_cards;
      if (yellow == null || red == null) return null;
      return Math.max(0, 1 - (yellow * 0.03 + red * 0.12));
    },
  },
  {
    key: 'form',
    label: 'Form',
    max: 15,
    getter: (player) => {
      const recent = player.recent_form ?? [];
      if (recent.length === 0) return null;

      const points = recent.reduce((acc, entry) => {
        if (entry.result === 'W') return acc + 3;
        if (entry.result === 'D') return acc + 1;
        return acc;
      }, 0);

      return points;
    },
  },
];

function toScaledPercent(value: number | null | undefined, max: number): number {
  if (value == null || max <= 0) return 0;
  const scaled = (value / max) * 100;
  return Math.max(0, Math.min(100, Number(scaled.toFixed(2))));
}

function toSeriesName(name: string | undefined, fallback: string): string {
  return name && name.trim().length > 0 ? name : fallback;
}

export function PlayerComparisonRadar({ player1, player2 }: PlayerComparisonRadarProps) {
  const leftSeries = toSeriesName(player1.name, 'Player 1');
  const rightSeriesBase = toSeriesName(player2.name, 'Player 2');
  const rightSeries = rightSeriesBase === leftSeries ? `${rightSeriesBase} (2)` : rightSeriesBase;

  const data = METRICS.map((metric) => ({
    metric: metric.label,
    [leftSeries]: toScaledPercent(metric.getter(player1), metric.max),
    [rightSeries]: toScaledPercent(metric.getter(player2), metric.max),
  }));

  return (
    <div className="h-[360px] w-full">
      <ResponsiveRadar
        data={data}
        keys={[leftSeries, rightSeries]}
        indexBy="metric"
        maxValue={100}
        margin={{ top: 40, right: 90, bottom: 50, left: 90 }}
        curve="linearClosed"
        borderWidth={2}
        borderColor={{ from: 'color' }}
        gridLabelOffset={18}
        dotSize={8}
        dotColor={{ theme: 'background' }}
        dotBorderWidth={2}
        dotBorderColor={{ from: 'color' }}
        colors={['#14b8a6', '#f59e0b']}
        blendMode="multiply"
        motionConfig="gentle"
        legends={[
          {
            anchor: 'top-left',
            direction: 'column',
            translateX: -70,
            translateY: -28,
            itemWidth: 100,
            itemHeight: 18,
            itemTextColor: '#cbd5e1',
            symbolSize: 12,
            symbolShape: 'circle',
          },
        ]}
        theme={{
          background: 'transparent',
          text: {
            fill: '#cbd5e1',
            fontSize: 12,
          },
          grid: {
            line: {
              stroke: '#334155',
              strokeWidth: 1,
            },
          },
          dots: {
            text: {
              fill: '#e2e8f0',
              fontSize: 11,
              fontWeight: 600,
            },
          },
          tooltip: {
            container: {
              background: '#0f172a',
              color: '#e2e8f0',
              borderRadius: 10,
              border: '1px solid #334155',
              fontSize: 12,
            },
          },
        }}
      />
    </div>
  );
}
