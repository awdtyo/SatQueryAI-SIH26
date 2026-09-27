import type { Config } from "tailwindcss";

/**
 * The UI uses Tailwind's stock `slate` (surfaces), `teal` (accent/interactive),
 * `emerald` (healthy), `amber` (standby) and `rose` (error) ramps directly, so
 * only fonts, shadows and animations are extended here.
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        mono: ['"JetBrains Mono"', '"Fira Code"', "ui-monospace", "monospace"],
        sans: ['"Inter"', "system-ui", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 12px rgba(20,184,166,0.25)",
      },
      keyframes: {
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "slide-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "slide-in-left": {
          "0%": { opacity: "0", transform: "translateX(-12px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        "slide-in-right": {
          "0%": { opacity: "0", transform: "translateX(12px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        /* sonar ping around the analysis core */
        "radar-ping": {
          "0%": { opacity: "0.6", transform: "scale(0.55)" },
          "100%": { opacity: "0", transform: "scale(1.7)" },
        },
        /* indeterminate progress bar sweep */
        shimmer: {
          "0%": { transform: "translateX(-110%)" },
          "100%": { transform: "translateX(410%)" },
        },
        /* boot-sequence terminal cursor */
        blink: {
          "0%, 45%": { opacity: "1" },
          "50%, 95%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.3s ease-out",
        "slide-up": "slide-up 0.4s ease-out",
        "slide-in-left": "slide-in-left 0.2s ease-out",
        "slide-in-right": "slide-in-right 0.2s ease-out",
        "radar-ping": "radar-ping 2.2s ease-out infinite",
        shimmer: "shimmer 1.8s ease-in-out infinite",
        blink: "blink 1.1s steps(1, end) infinite",
      },
    },
  },
  plugins: [],
} satisfies Config;
