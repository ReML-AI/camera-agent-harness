/** @type {import('tailwindcss').Config} */

// The review prototype hardcodes Tailwind's default `gray-*` and `blue-*` utilities
// across ~50 components. Rather than rewrite those call sites, the two scales are
// redefined here so the prototype inherits the demo's warm neutral palette and its
// single purple accent (demo/styles.css). Semantic green/amber/red are left on the
// Tailwind defaults so status colours keep their conventional meaning.
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Warm neutrals — matches --canvas #f2f2ee, --line #dcddd8, --ink #181b1a.
        gray: {
          50: "#f8f8f5",
          100: "#f2f2ee",
          200: "#dcddd8",
          300: "#c9cbc5",
          400: "#a4a8a2",
          500: "#6b706c",
          600: "#5d625e",
          700: "#454a47",
          800: "#2e3230",
          900: "#181b1a",
          950: "#0d0f0e",
        },
        // Harness accent — matches --purple #7255d9 / --purple-dark #5c43bb.
        blue: {
          50: "#f5f2ff",
          100: "#efebff",
          200: "#ded6fb",
          300: "#c4b6f6",
          400: "#9b83e9",
          500: "#7255d9",
          600: "#5c43bb",
          700: "#4b3699",
          800: "#3b2b78",
          900: "#2e2159",
          950: "#1c1438",
        },
      },
    },
  },
  plugins: [],
}
