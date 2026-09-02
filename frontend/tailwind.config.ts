import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Brighter aerospace-navy surfaces (kept same key names for compatibility)
        surface: {
          950: "#0A1017",
          900: "#0B1220",
          850: "#0F1726",
          800: "#131D2B",
          750: "#152030",
          700: "#172333",
          650: "#1B2A3B",
          600: "#1B2A3B",
          500: "#232F42",
          400: "#26394D",
        },
        accent: {
          DEFAULT: "#32D7FF",
          dim: "#1F9DB8",
          muted: "#2FB0C9",
          bright: "#6FE7FF",
          pale: "#A8EEFF",
        },
        signal: {
          green: "#35D58A",
          amber: "#F4C95D",
          red: "#FF6675",
        },
        ink: {
          DEFAULT: "#E6F0F7",
          secondary: "#91A6BA",
          muted: "#63788C",
        },
        muted: {
          DEFAULT: "#63788C",
          light: "#91A6BA",
          lighter: "#B7C8D8",
        },
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', '"Fira Code"', "ui-monospace", "monospace"],
        sans: ['"Inter"', "system-ui", "sans-serif"],
      },
      boxShadow: {
        panel: "inset 0 1px 0 0 rgba(230,240,247,0.05)",
        "panel-active": "inset 0 1px 0 0 rgba(50,215,255,0.14)",
      },
      keyframes: {
        scan: {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(100%)" },
        },
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "slide-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        scan: "scan 2.5s ease-in-out infinite",
        "fade-in": "fade-in 0.3s ease-out",
        "slide-up": "slide-up 0.4s ease-out",
      },
    },
  },
  plugins: [],
} satisfies Config;
