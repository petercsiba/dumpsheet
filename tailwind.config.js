/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./components/**/*.{js,ts,jsx,tsx}', './pages/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // 'accent-1': '#333',
        'black': '#191919',
        'green': '#D0D0CB',
        'white': '#F0F0EB',
      },
    },
  },
  variants: {},
  plugins: [],
}
