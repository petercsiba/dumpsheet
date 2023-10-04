/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./components/**/*.{js,ts,jsx,tsx}', './pages/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // 'accent-1': '#333',
        'black': '#000000',
        // 'gray': '#FDFDFD',
        'purple': '#B89FF0',
        'white': '#FFFFFF',
      },
    },
  },
  variants: {},
  plugins: [],
}
