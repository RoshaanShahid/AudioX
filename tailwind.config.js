// AUDIOX - WEBAPP/AudioX/tailwind.config.js
module.exports = {
  content: [
    // For templates directly under AUDIOX - WEBAPP/AudioX/templates/ (e.g., Homepage.html)
    './templates/**/*.html',
    // For templates within the AudioXApp application (covers AudioXApp/templates/AudioXApp/ and subfolders like user, creator, admin)
    './AudioXApp/templates/**/*.html',
    // If AudioXCore also has templates
    './AudioXCore/templates/**/*.html', 
    // If you use Tailwind classes directly in JavaScript files:
    './**/static/js/**/*.js', 
  ],
  theme: {
    extend: {
      colors: {
        // == Consolidated from Homepage.html & creator_base.html (theme- prefix) ==
        'theme-primary': '#091e65',
        'theme-primary-hover': '#071852', 
        'theme-primary-light': '#eef2ff', 
        'theme-primary-lighter': '#f0f5ff',
        'theme-primary-lightest': '#f9fafb',
        
        'theme-secondary': '#f97316', 
        'theme-secondary-hover': '#ea580c',
        'theme-secondary-light': '#fffbeb', // From homepage (distinct from creator theme-secondary)

        'theme-text-primary': '#1f2937',
        'theme-text-secondary': '#4b5563',
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
        
        'theme-error': '#ef4444',
        'theme-error-hover': '#dc2626',
        'theme-error-light': '#fee2e2', 
        
        'theme-warning': '#f97316', // Same as theme-secondary from creator_base
        'theme-warning-light': '#ffedd5', 

        'theme-border': '#e5e7eb',
        'theme-border-dark': '#374151',
        'theme-border-subtle': '#4b5563',
        'theme-border-light': '#f3f4f6',
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
        'theme-bg-error-light': '#fee2e2',

        'theme-bg-icon-yellow': '#fefce8',
        'theme-text-icon-yellow': '#b45309',
        'theme-bg-icon-green': '#f0fdf4',
        'theme-text-icon-green': '#15803d',
        'theme-bg-icon-blue': '#eff6ff',
        'theme-text-icon-blue': '#1d4ed8',
        'theme-bg-icon-purple': '#faf5ff',
        'theme-text-icon-purple': '#7e22ce',
        'theme-bg-icon-red': '#fef2f2',
        'theme-text-icon-red': '#b91c1c',

        // == From admin_base.html (brand- prefix) ==
        'brand-navy': '#091e65', // Same as theme-primary
        'brand-navy-dark': '#051240',
        'brand-navy-light': '#1c3a8a', // Homepage 'theme-primary-hover' was this
        'brand-navy-lighter': '#3b5bb5',
        'brand-navy-surface': 'rgba(9, 30, 101, 0.05)',
        'brand-bg': '#f0f2f5', // Admin specific page background
        'brand-surface': '#ffffff', // Admin specific card/surface background
        'brand-surface-alt': '#f8fafc', // Admin specific alternative surface
        'brand-border': '#e5e7eb', // Same as theme-border
        'brand-border-light': '#f1f3f9',
        'brand-text-primary': '#111827', // Admin specific primary text
        'brand-text-secondary': '#374151', // Admin specific secondary text
        'brand-text-muted': '#6b7280', // Same as theme-text-light
        'brand-text-on-navy': '#ffffff', // Same as theme-text-inverted
        'brand-text-on-accent': '#ffffff', // Same as theme-text-inverted
        'brand-accent': '#f97316', // Same as theme-secondary
        'brand-accent-dark': '#ea580c', // Same as theme-secondary-hover
        'brand-accent-light': '#fb923c',
        'brand-accent-surface': '#fff7ed',
        'brand-success': '#10b981', // Same as theme-success
        'brand-success-light': '#f0fdfa', // Similar to theme-green-lighter
        'brand-success-dark': '#047857',
        'brand-danger': '#ef4444', // Same as theme-error
        'brand-danger-light': '#fef2f2', // Similar to theme-bg-error-light
        'brand-danger-dark': '#b91c1c', // Similar to theme-text-icon-red
        'brand-warning': '#f59e0b', // Homepage 'theme-secondary' was this
        'brand-warning-light': '#fffbeb', // Same as theme-secondary-light from homepage
        'brand-warning-dark': '#d97706', // Homepage 'theme-secondary-hover' was this
        'brand-info': '#3b82f6',
        'brand-info-light': '#eff6ff', // Same as theme-bg-icon-blue
        'brand-info-dark': '#1d4ed8', // Same as theme-text-icon-blue
        'brand-purple': '#a855f7',
        'brand-purple-light': '#faf5ff', // Same as theme-bg-icon-purple
        'brand-purple-dark': '#9333ea',
        'brand-teal': '#14b8a6',
        'brand-teal-light': '#ccfbf1',
        'brand-teal-dark': '#0f766e',
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
      },
      boxShadow: {
        // Combined and de-duplicated
        'card': '0 1px 2px 0 rgba(0, 0, 0, 0.04)', 
        'card-lg': '0 4px 8px -2px rgba(0, 0, 0, 0.06), 0 2px 4px -2px rgba(0, 0, 0, 0.06)',
        'header': '0 2px 4px 0 rgba(0, 0, 0, 0.1)',
        'dropdown-dark': '0 10px 20px -5px rgba(0, 0, 0, 0.25), 0 4px 6px -4px rgba(0, 0, 0, 0.15)',
        'dropdown': '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -4px rgba(0, 0, 0, 0.1)',
        'lg': '0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)',
        'xl': '0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1)',
        'focus-ring': '0 0 0 3px rgba(9, 30, 101, 0.3)', 
        'focus-ring-light': '0 0 0 3px rgba(245, 158, 11, 0.4)',
        'focus-ring-inverted': '0 0 0 3px rgba(255, 255, 255, 0.3)',
        'inner-dark': 'inset 0 2px 4px 0 rgb(0 0 0 / 0.2)',
        'subtle': '0 1px 2px 0 rgba(0, 0, 0, 0.03)', // admin_base
        'input-focus': '0 0 0 2px #1c3a8a', // admin_base (value of brand-navy-light)
        'accent-glow': '0 0 15px 0px #fb923c', // admin_base (value of brand-accent-light)
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
        pulse: {
          '0%, 100%': { transform: 'scale(1)', opacity: '0.7' },
          '50%': { transform: 'scale(1.1)', opacity: '1' },
        }
      },
      animation: {
        pulse: 'pulse 1.5s infinite ease-in-out',
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
    require('@tailwindcss/forms'), // Ensure this is installed
  ],
}
