/** @type {import('tailwindcss').Config} */
// Semantic colour slots are backed by CSS custom properties (see index.css)
// so a single class set renders both light (.light/:root) and dark (html.dark).
const v = (name) => `rgb(var(${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        surface: v("--c-surface"), // card / raised surface
        onaccent: v("--c-onaccent"), // text on filled accent buttons
        ink: {
          50: v("--c-ink-50"),
          100: v("--c-ink-100"),
          200: v("--c-ink-200"),
          300: v("--c-ink-300"),
          400: v("--c-ink-400"),
          500: v("--c-ink-500"),
          600: v("--c-ink-600"),
          700: v("--c-ink-700"),
          800: v("--c-ink-800"),
          900: v("--c-ink-900"),
          950: v("--c-ink-950"),
        },
        signal: {
          400: v("--c-signal-400"),
          500: v("--c-signal-500"),
          600: v("--c-signal-600"),
        },
        amberish: {
          400: v("--c-amberish-400"),
          500: v("--c-amberish-500"),
          600: v("--c-amberish-600"),
        },
        red: {
          // themed overrides for the error panel + "missing both" badge only
          50: v("--c-red-50"),
          100: v("--c-red-100"),
          300: v("--c-red-300"),
          600: v("--c-red-600"),
          700: v("--c-red-700"),
          800: v("--c-red-800"),
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
