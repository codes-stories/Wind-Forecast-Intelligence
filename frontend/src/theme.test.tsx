import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import Header from "./components/Header";
import { ThemeProvider, initialTheme, useTheme } from "./theme";

function Probe() {
  const { theme, toggle } = useTheme();
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <button type="button" onClick={toggle}>
        toggle
      </button>
    </div>
  );
}

function setUrl(path: string) {
  window.history.replaceState({}, "", path);
}

beforeEach(() => {
  window.localStorage.clear();
  setUrl("/");
  document.documentElement.classList.remove("dark");
});

afterEach(() => {
  setUrl("/");
  document.documentElement.classList.remove("dark");
  window.localStorage.clear();
});

describe("theme mode", () => {
  it("defaults to light when nothing is stored", () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(screen.getByTestId("theme")).toHaveTextContent("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("toggles the dark class on <html> and persists the choice", async () => {
    const user = userEvent.setup();
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    await user.click(screen.getByRole("button", { name: "toggle" }));
    expect(screen.getByTestId("theme")).toHaveTextContent("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(window.localStorage.getItem("wfi-theme")).toBe("dark");

    await user.click(screen.getByRole("button", { name: "toggle" }));
    expect(screen.getByTestId("theme")).toHaveTextContent("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(window.localStorage.getItem("wfi-theme")).toBe("light");
  });

  it("applies the stored theme on mount (no toggle needed)", async () => {
    window.localStorage.setItem("wfi-theme", "dark");
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(screen.getByTestId("theme")).toHaveTextContent("dark");
    await waitFor(() => expect(document.documentElement.classList.contains("dark")).toBe(true));
  });

  it("?theme= URL param wins over the stored preference", () => {
    window.localStorage.setItem("wfi-theme", "dark");
    setUrl("/?theme=light");
    expect(initialTheme()).toBe("light");
    setUrl("/?theme=dark");
    window.localStorage.setItem("wfi-theme", "light");
    expect(initialTheme()).toBe("dark");
  });

  it("rejects an invalid stored value and falls back safely", () => {
    window.localStorage.setItem("wfi-theme", "neon");
    const theme = initialTheme();
    expect(theme === "light" || theme === "dark").toBe(true);
  });

  it("Header exposes an accessible theme switch", async () => {
    const user = userEvent.setup();
    render(
      <ThemeProvider>
        <Header health={null} />
      </ThemeProvider>,
    );
    const button = screen.getByRole("button", { name: "Switch to dark mode" });
    await user.click(button);
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(screen.getByRole("button", { name: "Switch to light mode" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Switch to light mode" }));
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });
});
