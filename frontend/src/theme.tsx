/** Light/dark theme state.
 *
 * Precedence: ?theme= URL param (deep-link/test) → localStorage → OS preference.
 * The `dark` class on <html> drives all CSS tokens (see index.css); chart
 * components read palette colours through useTheme().colors.
 * index.html applies the class before first paint to avoid a flash. */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { CHART_COLORS, type ChartColors, type ThemeMode } from "./lib/chartTheme";

const STORAGE_KEY = "wfi-theme";

function systemTheme(): ThemeMode {
  if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
    try {
      if (window.matchMedia("(prefers-color-scheme: dark)").matches) return "dark";
    } catch {
      /* matchMedia unavailable */
    }
  }
  return "light";
}

function urlTheme(): ThemeMode | null {
  if (typeof window === "undefined") return null;
  try {
    const param = new URLSearchParams(window.location.search).get("theme");
    return param === "dark" || param === "light" ? param : null;
  } catch {
    return null;
  }
}

export function initialTheme(): ThemeMode {
  const fromUrl = urlTheme();
  if (fromUrl) return fromUrl;
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "dark" || stored === "light") return stored;
  } catch {
    /* storage unavailable */
  }
  return systemTheme();
}

interface ThemeContextValue {
  theme: ThemeMode;
  setTheme: (next: ThemeMode) => void;
  toggle: () => void;
  colors: ChartColors;
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: "light",
  setTheme: () => undefined,
  toggle: () => undefined,
  colors: CHART_COLORS.light,
});

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeMode>(initialTheme);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    try {
      window.localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      /* storage unavailable */
    }
  }, [theme]);

  const setTheme = useCallback((next: ThemeMode) => setThemeState(next), []);
  const toggle = useCallback(
    () => setThemeState((current) => (current === "dark" ? "light" : "dark")),
    [],
  );

  const value = useMemo<ThemeContextValue>(
    () => ({ theme, setTheme, toggle, colors: CHART_COLORS[theme] }),
    [theme, setTheme, toggle],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}
