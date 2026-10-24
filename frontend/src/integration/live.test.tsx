/**
 * Optional live test: renders the dashboard against a REAL running backend.
 * Skipped by default. Run with:
 *   LIVE=1 VITE_API_BASE=http://127.0.0.1:8000 npm test
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "../App";

const live = process.env.LIVE === "1" ? describe : describe.skip;

live("live backend integration", () => {
  it(
    "renders real API-derived coverage and KPI values",
    async () => {
      render(<App />);
      expect(
        await screen.findByRole("heading", { name: "Wind Forecast Intelligence" }),
      ).toBeInTheDocument();
      // real coverage hint: "N of M intervals matched"
      expect(await screen.findByText(/of \d+ intervals matched/, {}, { timeout: 60000 })).toBeInTheDocument();
      expect(screen.getByText(/Decision cutoff: 09:20 UTC on D-1/)).toBeInTheDocument();
      expect(screen.getByText("MAE")).toBeInTheDocument();
    },
    90_000,
  );
});
