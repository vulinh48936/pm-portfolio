/** @type {import('tailwindcss').Config} */
// Palette theo vps-design-system.md (VPS Brand Guidelines 2024). KHÔNG thêm màu ngoài guideline.
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        vps: {
          violet: '#8229E3',     // primary — phải chiếm ≥20–30% diện tích màu
          black: '#1E1E1E',
          offwhite: '#F7F7F7',
          deep: '#2D0C44',       // deep violet (solid)
          lavender: '#E0DCF4',   // pale lavender (solid)
          lilac: '#E6CFFF',      // pale lilac (⚠ suy từ RGB 230,207,255)
          navy: '#041361',       // gradient stop
          navy2: '#021443',
          purple: '#6F41AD',     // gradient stop
          bright: '#7A34DC',
          gray: '#B8BABC',       // neutral gray
          // supporting / market colors
          green: '#7FD08C',      // Growth Green — tăng
          yellow: '#F9E9CC',     // Reference Yellow — tham chiếu
          red: '#EACACF',        // Potential Red — giảm
          blue: '#87B4DD',       // Trust Blue — sàn
        },
      },
      fontFamily: {
        // Forma DJR Display cần license thương mại; fallback Arial theo guideline §4.2
        sans: ['"Forma DJR Display"', 'Arial', 'Helvetica', 'sans-serif'],
      },
      letterSpacing: {
        vps: '0.03em',           // tracking +30 (đơn vị design tool ≈ 0.03em)
        'vps-wide': '0.04em',    // +40 cho CTA
      },
      backgroundImage: {
        'vps-gradient': 'linear-gradient(135deg, #041361 0%, #6F41AD 100%)',
        'vps-gradient-2': 'linear-gradient(135deg, #021443 0%, #7A34DC 100%)',
      },
      borderRadius: { vps: '10px' },
    },
  },
  plugins: [],
}
