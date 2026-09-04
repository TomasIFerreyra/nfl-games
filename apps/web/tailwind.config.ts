import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#0d1117",
        surface: "#161b22",
        "surface-raised": "#21262d",
        border: "#30363d",
        "nfl-blue": "#013369",
        "nfl-red": "#D50A0A",
        tier: {
          yellow: "#FBBF24",
          green: "#34D399",
          blue: "#60A5FA",
          purple: "#A78BFA",
        },
      },
    },
  },
  plugins: [],
};

export default config;
