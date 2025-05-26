// AUDIOX - WEBAPP/AudioX/tailwind.config.js
module.exports = {
  content: [
    './templates/**/*.html',
    './AudioXApp/templates/**/*.html',
    './AudioXCore/templates/**/*.html', 
    './**/static/js/**/*.js', 
  ],
  theme: {
    extend: {
      colors: {
        // == Defined for the Ultra-Elegant Light UI ==
        'theme-primary': '#091e65',
        'theme-primary-hover': '#071852',
        'theme-primary-text-on-light': '#091e65',
        'theme-primary-bg-ultra-light': 'rgba(9, 30, 101, 0.02)',
        'theme-primary-bg-subtle': 'rgba(9, 30, 101, 0.04)', // Added for slightly more emphasis if needed
        'theme-primary-border-light': 'rgba(9, 30, 101, 0.1)',
        'theme-primary-border-subtle': 'rgba(9, 30, 101, 0.15)', // Renamed from HTML comment
        'theme-primary-focus-ring': 'rgba(9, 30, 101, 0.25)',

        'theme-error': '#ef4444', // Red (e.g., Tailwind red-500)
        'theme-error-hover': '#dc2626', // Darker Red (e.g., Tailwind red-600)
        'theme-error-text': '#b91c1c', 
        'theme-error-bg-ultra-light': 'rgba(239, 68, 68, 0.03)',
        'theme-error-bg-subtle': 'rgba(239, 68, 68, 0.05)', // Added for slightly more emphasis
        'theme-error-border-light': 'rgba(239, 68, 68, 0.15)',
        'theme-error-border-subtle': 'rgba(239, 68, 68, 0.2)', // Renamed from HTML comment
        'theme-error-focus-ring': 'rgba(239, 68, 68, 0.3)',

        'text-secondary-on-light': '#566172', 
        'border-strong-on-light': '#d1d5db', // For main input borders
        'border-soft-on-light': '#e5e7eb',   // For dividers
        'placeholder-text-on-light': '#a0aec0', 
        'white': '#ffffff',
        'off-white-bg': '#f9fafb',

        // == Retained from your existing config (can be reviewed/pruned) ==
        'theme-primary-light': '#eef2ff', 
        'theme-primary-lighter': '#f0f5ff',
        'theme-primary-lightest': '#f9fafb',
        'theme-secondary': '#f97316', 
        'theme-secondary-hover': '#ea580c',
        'theme-secondary-light': '#fffbeb',
        'theme-text-light': '#6b7280',
        'theme-text-inverted': '#ffffff', 
        'theme-text-inverted-muted': '#e5e7eb', 
        'theme-text-inverted-subtle': '#9ca3af',
        'theme-text-nav-dark-bg': '#cbd5e1',
        'theme-text-nav-dark-bg-hover': '#ffffff',
        'theme-text-nav-dark-bg-active': '#ffffff',
        'theme-success': '#10b981',
        'theme-green': '#16a34a',
        'theme-green-hover': '#15803d',
        'theme-green-light': '#d1fae5',
        'theme-green-lighter': '#f0fdf4',
        'theme-warning': '#f97316', 
        'theme-warning-light': '#ffedd5', 
        'theme-border': '#e5e7eb', 
        'theme-border-dark': '#374151',
        'theme-border-dark-nav': '#1e3a8a',
        'theme-bg-subtle': '#f9fafb', 
        'theme-bg-dark-menu': '#081a56',
        'theme-bg-dark-hover': 'rgba(255, 255, 255, 0.1)', 
        'theme-bg-dark-active': 'rgba(255, 255, 255, 0.15)',
        'theme-bg-nav-dark-bg-active': 'rgba(255, 255, 255, 0.1)',
        'theme-bg-nav-dark-bg-hover': 'rgba(255, 255, 255, 0.05)',
        'theme-input-bg': '#ffffff',
        'theme-input-bg-focus': '#ffffff',
        'theme-bg-page': '#f8fafc', 
        'theme-bg-card': '#ffffff', 
        'theme-bg-header': '#091e65',
        'theme-bg-icon-yellow': '#fefce8',
        'theme-text-icon-yellow': '#b45309',
        'theme-bg-icon-green': '#f0fdf4',
        'theme-text-icon-green': '#15803d',
        'theme-bg-icon-blue': '#eff6ff',
        'theme-text-icon-blue': '#1d4ed8',
        'theme-bg-icon-purple': '#faf5ff',
        'theme-text-icon-purple': '#7e22ce',
        'theme-bg-icon-red': '#fef2f2',
        'brand-navy': '#091e65', 
        'brand-navy-dark': '#051240',
        'brand-navy-light': '#1c3a8a', 
        'brand-navy-lighter': '#3b5bb5',
        'brand-navy-surface': 'rgba(9, 30, 101, 0.05)',
        'brand-bg': '#f0f2f5', 
        'brand-surface': '#ffffff', 
        'brand-surface-alt': '#f8fafc', 
        'brand-border': '#e5e7eb', 
        'brand-border-light': '#f1f3f9',
        'brand-text-primary': '#111827', 
        'brand-text-secondary': '#374151', 
        'brand-text-muted': '#6b7280', 
        'brand-text-on-navy': '#ffffff', 
        'brand-text-on-accent': '#ffffff', 
        'brand-accent': '#f97316', 
        'brand-accent-dark': '#ea580c', 
        'brand-accent-light': '#fb923c',
        'brand-accent-surface': '#fff7ed',
        'brand-success': '#10b981', 
        'brand-success-light': '#f0fdfa', 
        'brand-success-dark': '#047857',
        'brand-danger': '#ef4444', 
        'brand-danger-light': '#fef2f2', 
        'brand-danger-dark': '#b91c1c', 
        'brand-warning': '#f59e0b', 
        'brand-warning-light': '#fffbeb', 
        'brand-warning-dark': '#d97706', 
        'brand-info': '#3b82f6',
        'brand-info-light': '#eff6ff', 
        'brand-info-dark': '#1d4ed8', 
        'brand-purple': '#a855f7',
        'brand-purple-light': '#faf5ff', 
        'brand-purple-dark': '#9333ea',
        'brand-teal': '#14b8a6',
        'brand-teal-light': '#ccfbf1',
        'brand-teal-dark': '#0f766e',
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
      },
      boxShadow: {
        'card': '0 1px 2px 0 rgba(0, 0, 0, 0.04)',
        'card-lg': '0 4px 8px -2px rgba(0, 0, 0, 0.06), 0 2px 4px -2px rgba(0, 0, 0, 0.06)',
        'header': '0 2px 4px 0 rgba(0, 0, 0, 0.1)',
        'dropdown-dark': '0 10px 20px -5px rgba(0, 0, 0, 0.25), 0 4px 6px -4px rgba(0, 0, 0, 0.15)',
        'dropdown': '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -4px rgba(0, 0, 0, 0.1)',
        'focus-ring': '0 0 0 3px rgba(9, 30, 101, 0.3)', 
        'focus-ring-light': '0 0 0 3px rgba(245, 158, 11, 0.4)',
        'focus-ring-inverted': '0 0 0 3px rgba(255, 255, 255, 0.3)',
        'focus-ring-error': '0 0 0 3px rgba(239, 68, 68, 0.3)', 
        'focus-ring-success': '0 0 0 3px rgba(16, 185, 129, 0.3)', 
        'inner-dark': 'inset 0 2px 4px 0 rgb(0 0 0 / 0.2)',
        'subtle': '0 1px 2px 0 rgba(0, 0, 0, 0.03)', 
        'input-base': '0 1px 2px 0 rgb(0 0 0 / 0.05)',
        'input-focus-primary': '0 0 0 3px rgba(9, 30, 101, 0.2)', 
        'button-primary-base': '0 4px 6px -1px rgba(9, 30, 101, 0.1), 0 2px 4px -2px rgba(9, 30, 101, 0.1)',
        'button-primary-hover-elevated': '0 10px 15px -3px rgba(9, 30, 101, 0.1), 0 4px 6px -4px rgba(9, 30, 101, 0.1)',
        'accent-glow': '0 0 15px 0px #fb923c', 
      },
      transitionProperty: {
        'height': 'height',
        'spacing': 'margin, padding',
        'max-height': 'max-height',
        'bg-color': 'background-color',
        'text-color': 'color',
        'border-color': 'border-color',
        'opacity': 'opacity',
        'transform': 'transform',
        'opacity-transform': 'opacity, transform',
        'colors-transform': 'background-color, border-color, color, fill, stroke, opacity, transform',
      },
      borderRadius: {
        'xl': '0.75rem', 
        '2xl': '1rem',
        'dropdown': '0.875rem', 
        '3xl': '1.5rem', 
      },
      keyframes: {
        // Existing keyframes
        pulse: { 
          '0%, 100%': { transform: 'scale(1)', opacity: '0.7' },
          '50%': { transform: 'scale(1.1)', opacity: '1' },
        },
        'fade-in': { 
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' }
        },
        // New/Updated keyframes for the contact support page
        fadeInLoad: { 
          '0%': { opacity: '0' }, 
          '100%': { opacity: '1' } 
        },
        // fadeInSection is now handled by JS class toggle + transition in CSS
        subtleButtonPulse: { 
          '0%, 100%': { transform: 'scale(1)' }, 
          '50%': { transform: 'scale(1.02)' } 
        },
      },
      animation: {
        // Existing animations
        pulse: 'pulse 1.5s infinite ease-in-out', 
        'fade-in': 'fade-in 0.5s ease-out forwards', 
        // New/Updated animations for the contact support page
        'fade-in-load': 'fadeInLoad 0.7s ease-out forwards', // Adjusted duration
        'subtle-button-pulse': 'subtleButtonPulse 2.5s infinite ease-in-out',
      },
      backgroundImage: {
        'sidebar-graphic': "linear-gradient(170deg, #091e65 30%, #051240 100%)", 
        'chart-placeholder-pattern': "url(\"data:image/svg+xml,%3Csvg width='52' height='26' viewBox='0 0 52 26' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23e5e7eb' fill-opacity='0.4'%3E%3Cpath d='M10 10c0-2.21-1.79-4-4-4-3.314 0-6-2.686-6-6h2c0 2.21 1.79 4 4 4 3.314 0 6 2.686 6 6 0 2.21 1.79 4 4 4 3.314 0 6 2.686 6 6 0 2.21 1.79 4 4 4v2c-3.314 0-6-2.686-6-6 0-2.21-1.79-4-4-4-3.314 0-6-2.686-6-6zm25.464-1.95l8.486 8.486-1.414 1.414-8.486-8.486 1.414-1.414z' /%3E%3C/g%3E%3C/g%3E%3C/svg%3E\")",
        'earnings-gradient': "linear-gradient(105deg, #091e65 0%, #1c3a8a 100%)",
      },
      transitionTimingFunction: {
        'elastic': 'cubic-bezier(0.68, -0.55, 0.27, 1.55)',
        'smooth': 'cubic-bezier(0.4, 0, 0.2, 1)',
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms'), 
  ],
}
