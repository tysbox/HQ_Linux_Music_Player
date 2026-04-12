import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        surface: {
          base:      '#0a0a0a',
          panel:     '#0d0d0d',
          bar:       '#111111',
          card:      '#141414',
          cardInner: '#1a1a1a',
        },
        accent: {
          green:  '#22c55e',
          blue:   '#3b82f6',
          amber:  '#eab308',
          red:    '#ef4444',
          purple: '#a855f7',
        },
        dial: {
          hum:       '#ef4444',
          eq:        '#3b82f6',
          reverb:    '#eab308',
          crossfeed: '#a855f7',
        },
        vu: {
          low:  '#22c55e',
          mid:  '#eab308',
          peak: '#ef4444',
        },
      },
      fontSize: {
        '2xs': '8px',
        'xs':  '9px',
        'sm':  '10px',
      },
      borderRadius: {
        'sm': '5px',
        'md': '6px',
        'lg': '8px',
      },
      spacing: {
        '84': '84px',
      },
      screens: {
        'md': '768px',
      },
    },
  },
  plugins: [],
}
export default config
