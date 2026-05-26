/** @type {import('tailwindcss').Config} */
export default {
  content: ["./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}"],
  theme: {
    extend: {
      colors: {
        paper: {
          DEFAULT: "#f7f3e9",
          tint: "#efe9d8",
          deep: "#e7dfca",
        },
        ink: {
          900: "#1a1a1a",
          700: "#3a3a3a",
          500: "#6a6a6a",
          300: "#a7a094",
        },
        forest: {
          900: "#13251c",
          700: "#1f3d2b",
          500: "#3a6c4b",
          300: "#6b8e7f",
          100: "#c8d6cd",
        },
        umber: {
          900: "#5a2a10",
          700: "#8b3f1d",
          500: "#b65724",
          300: "#d8895b",
        },
        sepia: {
          700: "#5a4f3a",
          500: "#837d6a",
          300: "#b0a890",
        },
        signal: {
          verified: "#2f6b3a",
          disputed: "#b65724",
          unverified: "#837d6a",
        },
      },
      fontFamily: {
        display: ["'Libre Bodoni'", "Bodoni Moda", "Didot", "serif"],
        sans: ["'Public Sans'", "Inter", "system-ui", "-apple-system", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: {
        kicker: ["0.7rem", { lineHeight: "1.1", letterSpacing: "0.18em" }],
        "display-1": ["clamp(2.5rem, 6vw, 4.5rem)", { lineHeight: "0.98", letterSpacing: "-0.02em" }],
        "display-2": ["clamp(1.875rem, 4vw, 2.75rem)", { lineHeight: "1.05", letterSpacing: "-0.015em" }],
      },
      maxWidth: {
        prose: "62ch",
        narrow: "44ch",
      },
      gridTemplateColumns: {
        editorial: "minmax(0, 1.4fr) minmax(0, 1fr)",
        "editorial-wide": "minmax(0, 2fr) minmax(0, 1fr)",
      },
    },
  },
  plugins: [],
};
