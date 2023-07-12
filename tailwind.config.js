/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./components/**/*.{js,ts,jsx,tsx}', './pages/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // 'accent-1': '#333',
        'accent-1': '#981161',  // Tailwind default purple is a855f7
        'purple': '#a21063',  // gradient [350e47, dd1173]
      },
    },
  },
  variants: {},
  plugins: [],
}
