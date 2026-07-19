/** @type {import('tailwindcss').Config}*/ 

export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#F7F6F1",
        panel: "#EFEDE4",
        panelhover: "#E7E4D7",
        ink: "#1B1D23",
        inksoft: "#63665F",
        inkfaint: "#9A9C90",
        line: "#DEDACB",
        indigo: {
          DEFAULT: "#3648C7",
          dark: "#2A38A0",
          soft: "#EAEBFA",
        },
        amber: {
          DEFAULT: "#C98A2A",
          soft: "#F6E8C8",
          softer: "#FBF2DD",
        },
      },
      fontFamily: {
        display: ["Fraunces", "serif"],
        sans: ["Inter", "sans-serif"],
        mono: ['"IBM Plex Mono"', "monospace"],
      },
      borderRadius: {
        card: "14px",
      },
    },
  },
  plugins: [],
};
