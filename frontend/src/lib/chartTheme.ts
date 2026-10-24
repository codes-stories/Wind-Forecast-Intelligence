/** Recharts palettes per theme. SVG stroke/fill attributes need concrete
 *  colour strings (no var() substitution), so chart colours are resolved in
 *  JS from the active theme instead of CSS classes. */
export type ThemeMode = "light" | "dark";

export interface ChartColors {
  grid: string;
  axis: string;
  reference: string;
  forecast: string;
  actual: string;
  bar: string;
  flag: string;
  eligible: string;
  postCutoff: string;
  selected: string;
  actualRef: string;
}

export const CHART_COLORS: Record<ThemeMode, ChartColors> = {
  light: {
    grid: "#eceef2",
    axis: "#66748c",
    reference: "#b0bac9",
    forecast: "#3b7fc4",
    actual: "#c98d1e",
    bar: "#5b9bd5",
    flag: "#c98d1e",
    eligible: "#5b9bd5",
    postCutoff: "#c98d1e",
    selected: "#3b7fc4",
    actualRef: "#1f9d6b",
  },
  dark: {
    grid: "#262c38",
    axis: "#8b96a8",
    reference: "#424c5f",
    forecast: "#6aa9e8",
    actual: "#d9a13b",
    bar: "#6aa9e8",
    flag: "#d9a13b",
    eligible: "#6aa9e8",
    postCutoff: "#d9a13b",
    selected: "#6aa9e8",
    actualRef: "#2fb385",
  },
};
