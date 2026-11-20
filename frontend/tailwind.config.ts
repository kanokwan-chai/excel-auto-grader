import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-noto-thai)", "var(--font-sarabun)", "sans-serif"],
      },
      colors: {
        pastel: {
          cream: "#FFFDF9",
          lavender: "#F3EEFF",
          purple: "#7C3AED",
          purpleSoft: "#A78BFA",
          pink: "#FCE7F3",
          pinkAccent: "#EC4899",
          mint: "#D1FAE5",
          mintAccent: "#10B981",
          sky: "#E0F2FE",
          skyAccent: "#0284C7",
          peach: "#FFEDD5",
        },
      },
      boxShadow: {
        soft: "0 8px 30px -10px rgba(124, 58, 237, 0.12)",
        card: "0 4px 20px -6px rgba(109, 40, 217, 0.08)",
      },
      borderRadius: {
        "2xl": "1rem",
        "3xl": "1.5rem",
      },
    },
  },
  plugins: [],
};

export default config;
