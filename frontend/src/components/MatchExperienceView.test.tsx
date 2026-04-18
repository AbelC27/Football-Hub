import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { MatchExperienceView } from "@/components/MatchExperienceView";
import type { MatchExperience } from "@/lib/api";

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: ReactNode; href: string }) => <a href={href}>{children}</a>,
}));

const basePayload: MatchExperience = {
  header: {
    match_id: 5000,
    start_time: "2026-04-18T18:00:00Z",
    status: "LIVE",
    score: {
      home: 2,
      away: 1,
    },
    competition: {
      id: 39,
      name: "Premier League",
      country: "England",
      logo_url: null,
    },
  },
  teams: {
    home: {
      id: 1001,
      name: "Home FC",
      logo_url: null,
      stadium: "Home Stadium",
    },
    away: {
      id: 1002,
      name: "Away FC",
      logo_url: null,
      stadium: "Away Stadium",
    },
  },
  prediction: {
    id: 9000,
    match_id: 5000,
    home_win_prob: 52,
    draw_prob: 24,
    away_win_prob: 24,
    confidence_score: 0.72,
  },
  events: [
    {
      id: 8001,
      minute: 11,
      event_type: "goal",
      team_id: 1001,
      player_name: "Home Player 1",
      assist_player: "Home Player 7",
      card_type: null,
      detail: "Open Play Goal",
    },
  ],
  lineups: {
    home_starting_xi: [
      { id: 2001, name: "Home Player 1", position: "Forward", photo_url: null },
    ],
    away_starting_xi: [
      { id: 3001, name: "Away Player 1", position: "Defender", photo_url: null },
    ],
    substitutions: [
      {
        id: 8100,
        minute: 66,
        team_id: 1001,
        player_name: "Home Player 12",
        detail: "Home Player 12 in for Home Player 5",
      },
    ],
    source: "estimated",
  },
  form: {
    home_last_five: [
      {
        match_id: 1,
        start_time: "2026-04-10T18:00:00Z",
        status: "FT",
        opponent_name: "Team X",
        opponent_logo: null,
        is_home: true,
        team_score: 2,
        opponent_score: 0,
        result: "W",
        competition_name: "Premier League",
      },
    ],
    away_last_five: [
      {
        match_id: 2,
        start_time: "2026-04-10T19:00:00Z",
        status: "FT",
        opponent_name: "Team Y",
        opponent_logo: null,
        is_home: false,
        team_score: 1,
        opponent_score: 1,
        result: "D",
        competition_name: "Premier League",
      },
    ],
  },
  squads: {
    home: [
      { id: 2001, name: "Home Player 1", position: "Forward", photo_url: null },
    ],
    away: [
      { id: 3001, name: "Away Player 1", position: "Defender", photo_url: null },
    ],
  },
  partial_failures: [],
};

describe("MatchExperienceView", () => {
  it("renders core sections and event timeline", () => {
    render(<MatchExperienceView data={basePayload} />);

    expect(screen.getByText("Home FC")).toBeInTheDocument();
    expect(screen.getByText("Away FC")).toBeInTheDocument();
    expect(screen.getByText("AI Prediction")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Events" }));
    expect(screen.getByText("Goals, Assists and Cards")).toBeInTheDocument();
    expect(screen.getByText("Home Player 1")).toBeInTheDocument();
  });

  it("shows empty states for missing event and lineup data", () => {
    render(
      <MatchExperienceView
        data={{
          ...basePayload,
          events: [],
          lineups: {
            ...basePayload.lineups,
            home_starting_xi: [],
            away_starting_xi: [],
            substitutions: [],
          },
        }}
      />
    );

    fireEvent.click(screen.getByRole("tab", { name: "Events" }));
    expect(screen.getByText("No events recorded yet.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Lineups" }));
    expect(screen.getAllByText("No lineup available.").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("No substitutions recorded.")).toBeInTheDocument();
  });
});
