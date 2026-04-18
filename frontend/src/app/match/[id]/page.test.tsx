import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import type { MatchExperience } from "@/lib/api";
import MatchDetailsPage from "@/app/match/[id]/page";

const mockUseQuery = vi.fn();
const mockUseParams = vi.fn();
const mockSetQueryData = vi.fn();

vi.mock("@tanstack/react-query", () => ({
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
  useQueryClient: () => ({
    setQueryData: mockSetQueryData,
  }),
}));

vi.mock("next/navigation", () => ({
  useParams: () => mockUseParams(),
}));

vi.mock("@/hooks/useWebSocket", () => ({
  useWebSocket: () => null,
}));

vi.mock("@/components/MatchExperienceView", () => ({
  MatchExperienceView: ({ data }: { data: MatchExperience }) => <div>rendered:{data.teams.home.name}</div>,
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  },
}));

const payload: MatchExperience = {
  header: {
    match_id: 5000,
    start_time: "2026-04-18T18:00:00Z",
    status: "NS",
    score: { home: null, away: null },
    competition: null,
  },
  teams: {
    home: { id: 1001, name: "Home FC", logo_url: null, stadium: null },
    away: { id: 1002, name: "Away FC", logo_url: null, stadium: null },
  },
  prediction: null,
  events: [],
  lineups: {
    home_starting_xi: [],
    away_starting_xi: [],
    substitutions: [],
    source: "estimated",
  },
  form: {
    home_last_five: [],
    away_last_five: [],
  },
  squads: {
    home: [],
    away: [],
  },
  partial_failures: [],
};

describe("MatchDetailsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders match view when query succeeds", () => {
    mockUseParams.mockReturnValue({ id: "5000" });
    mockUseQuery.mockReturnValue({
      isPending: false,
      isError: false,
      isSuccess: true,
      data: payload,
      error: null,
      refetch: vi.fn(),
    });

    render(<MatchDetailsPage />);

    expect(screen.getByText("rendered:Home FC")).toBeInTheDocument();
  });

  it("renders invalid id fallback when route param is malformed", () => {
    mockUseParams.mockReturnValue({ id: "invalid-id" });
    mockUseQuery.mockReturnValue({
      isPending: false,
      isError: false,
      isSuccess: false,
      data: null,
      error: null,
      refetch: vi.fn(),
    });

    render(<MatchDetailsPage />);

    expect(screen.getByText("The match id is invalid. Please open this page from a valid match link.")).toBeInTheDocument();
  });
});
