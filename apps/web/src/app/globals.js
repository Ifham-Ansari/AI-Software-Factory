import { StyleSheet } from 'react-native';

export default StyleSheet.create({
  // * Design tokens and component styles.
 *
 * Plain CSS with custom properties rather than a utility framework: Phase 1 has a handful
 * of screens, and a dependency plus a build step would be infrastructure for its own sake.
 * Tokens mean a design system can be dropped in later without touching every component.
  ':root': {
    'Bg': '#0b0e14',
    'Surface': '#131823',
    'SurfaceRaised': '#1a2030',
    'Border': [{ 'unit': 'string', 'value': '#262d3d' }],
    'Text': '#e6e9f0',
    'TextMuted': '#939cb0',
    'Accent': '#4f7cff',
    'AccentHover': '#6b91ff',
    'AccentSoft': 'rgb(79 124 255 / 0.12)',
    'Danger': '#e5484d',
    'Success': '#3dd68c',
    'Radius': '8px',
    'RadiusLg': '14px',
    'Space1': '0.25rem',
    'Space2': '0.5rem',
    'Space3': '0.75rem',
    'Space4': '1rem',
    'Space6': '1.5rem',
    'Space8': '2rem',
    'ShadowCard': '0 1px 2px rgb(0 0 0 / 0.2), 0 12px 32px -16px rgb(0 0 0 / 0.5)',
    'ShadowRaised': '0 20px 48px -20px rgb(0 0 0 / 0.65)',
    'Font': [{ 'unit': 'string', 'value': 'ui-sans-serif,' }, { 'unit': 'em', 'value': NaN }, { 'unit': 'em', 'value': NaN }, { 'unit': 'string', 'value': '"Segoe' }, { 'unit': 'string', 'value': 'UI",' }, { 'unit': 'string', 'value': 'Roboto,' }, { 'unit': 'string', 'value': 'sans-serif' }],
    'FontMono': 'ui-monospace, "SF Mono", Menlo, Consolas, monospace'
  },
  '*': {
    'boxSizing': 'border-box'
  },
  '*::before': {
    'boxSizing': 'border-box'
  },
  '*::after': {
    'boxSizing': 'border-box'
  },
  'body': {
    'margin': [{ 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }],
    'background': 'var(--bg)',
    'color': 'var(--text)',
    'fontFamily': 'var(--font)',
    'lineHeight': [{ 'unit': 'px', 'value': 1.5 }],
    'WebkitFontSmoothing': 'antialiased'
  },
  'a': {
    'color': 'var(--accent)',
    'textDecoration': 'none'
  },
  'a:hover': {
    'textDecoration': 'underline'
  },
  // A visible focus ring is an accessibility requirement, not a style choice.
  ':focus-visible': {
    'outline': '2px solid var(--accent)',
    'outlineOffset': '2px'
  },
  'h1': {
    'fontSize': [{ 'unit': 'rem', 'value': 1.5 }],
    'margin': [{ 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }, { 'unit': 'string', 'value': 'var(--space-4)' }, { 'unit': 'px', 'value': 0 }]
  },
  'h2': {
    'fontSize': [{ 'unit': 'rem', 'value': 1.125 }],
    'margin': [{ 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }, { 'unit': 'string', 'value': 'var(--space-3)' }, { 'unit': 'px', 'value': 0 }]
  },
  'h3': {
    'fontSize': [{ 'unit': 'rem', 'value': 1 }],
    'margin': [{ 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }]
  },
  'muted': {
    'color': 'var(--text-muted)'
  },
  // ---------- Buttons ----------
  'btn': {
    'display': 'inline-flex',
    'alignItems': 'center',
    'justifyContent': 'center',
    'gap': 'var(--space-2)',
    'border': [{ 'unit': 'px', 'value': 1 }, { 'unit': 'string', 'value': 'solid' }, { 'unit': 'string', 'value': 'transparent' }],
    'borderRadius': 'var(--radius)',
    'font': [{ 'unit': 'string', 'value': 'inherit' }],
    'fontWeight': '500',
    'cursor': 'pointer',
    'transition': 'background-color 0.15s ease, border-color 0.15s ease, transform 0.1s ease,
    box-shadow 0.15s ease'
  },
  'btn:active:not(:disabled)': {
    'transform': 'translateY(1px)'
  },
  'btn-md': {
    'padding': [{ 'unit': 'string', 'value': 'var(--space-2)' }, { 'unit': 'string', 'value': 'var(--space-2)' }, { 'unit': 'string', 'value': 'var(--space-4)' }, { 'unit': 'string', 'value': 'var(--space-2)' }]
  },
  'btn-sm': {
    'padding': [{ 'unit': 'string', 'value': 'var(--space-1)' }, { 'unit': 'string', 'value': 'var(--space-1)' }, { 'unit': 'string', 'value': 'var(--space-3)' }, { 'unit': 'string', 'value': 'var(--space-1)' }],
    'fontSize': [{ 'unit': 'rem', 'value': 0.875 }]
  },
  'btn-block': {
    'width': [{ 'unit': '%H', 'value': 1 }]
  },
  'btn:disabled': {
    'opacity': '0.6',
    'cursor': 'not-allowed'
  },
  'btn-primary': {
    'background': 'var(--accent)',
    'color': '#fff',
    'boxShadow': [{ 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 1 }, { 'unit': 'px', 'value': 2 }, { 'unit': 'string', 'value': 'rgb(0 0 0 / 0.3)' }, { 'unit': 'string', 'value': 'rgb(0 0 0 / 0.3),' }, { 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }, { 'unit': 'string', 'value': 'var(--accent-soft)' }]
  },
  'btn-primary:hover:not(:disabled)': {
    'background': 'var(--accent-hover)',
    'boxShadow': [{ 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 4 }, { 'unit': 'px', 'value': 16 }, { 'unit': 'px', 'value': -4 }, { 'unit': 'string', 'value': 'rgb(79 124 255 / 0.5)' }]
  },
  'btn-secondary': {
    'background': 'var(--surface-raised)',
    'color': 'var(--text)',
    'borderColor': 'var(--border)'
  },
  'btn-danger': {
    'background': 'var(--danger)',
    'color': '#fff'
  },
  'btn-ghost': {
    'background': 'transparent',
    'color': 'var(--text-muted)'
  },
  'btn-ghost:hover:not(:disabled)': {
    'color': 'var(--text)'
  },
  'spinner': {
    'width': [{ 'unit': 'em', 'value': 0.875 }],
    'height': [{ 'unit': 'em', 'value': 0.875 }],
    'border': [{ 'unit': 'px', 'value': 2 }, { 'unit': 'string', 'value': 'solid' }, { 'unit': 'string', 'value': 'currentColor' }],
    'borderRightColor': 'transparent',
    'borderRadius': '50%',
    'animation': 'spin 0.6s linear infinite',
    'prefers-reduced-motion reduc': {
      'animationDuration': '2s'
    }
  },
  // Respect a reduced-motion preference.
  // ---------- Forms ----------
  'field': {
    'marginBottom': [{ 'unit': 'string', 'value': 'var(--space-4)' }]
  },
  'field label': {
    'display': 'block',
    'marginBottom': [{ 'unit': 'string', 'value': 'var(--space-1)' }],
    'fontSize': [{ 'unit': 'rem', 'value': 0.875 }],
    'fontWeight': '500'
  },
  'field input': {
    'width': [{ 'unit': '%H', 'value': 1 }],
    'padding': [{ 'unit': 'string', 'value': 'var(--space-2)' }, { 'unit': 'string', 'value': 'var(--space-2)' }, { 'unit': 'string', 'value': 'var(--space-3)' }, { 'unit': 'string', 'value': 'var(--space-2)' }],
    'background': 'var(--bg)',
    'border': [{ 'unit': 'px', 'value': 1 }, { 'unit': 'string', 'value': 'solid' }, { 'unit': 'string', 'value': 'var(--border)' }],
    'borderRadius': 'var(--radius)',
    'color': 'var(--text)',
    'font': [{ 'unit': 'string', 'value': 'inherit' }],
    'transition': 'border-color 0.15s ease, box-shadow 0.15s ease'
  },
  'field textarea': {
    'width': [{ 'unit': '%H', 'value': 1 }],
    'padding': [{ 'unit': 'string', 'value': 'var(--space-2)' }, { 'unit': 'string', 'value': 'var(--space-2)' }, { 'unit': 'string', 'value': 'var(--space-3)' }, { 'unit': 'string', 'value': 'var(--space-2)' }],
    'background': 'var(--bg)',
    'border': [{ 'unit': 'px', 'value': 1 }, { 'unit': 'string', 'value': 'solid' }, { 'unit': 'string', 'value': 'var(--border)' }],
    'borderRadius': 'var(--radius)',
    'color': 'var(--text)',
    'font': [{ 'unit': 'string', 'value': 'inherit' }],
    'transition': 'border-color 0.15s ease, box-shadow 0.15s ease'
  },
  'field input:focus': {
    'borderColor': 'var(--accent)',
    'boxShadow': [{ 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 3 }, { 'unit': 'string', 'value': 'var(--accent-soft)' }],
    'outline': 'none'
  },
  'field textarea:focus': {
    'borderColor': 'var(--accent)',
    'boxShadow': [{ 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 3 }, { 'unit': 'string', 'value': 'var(--accent-soft)' }],
    'outline': 'none'
  },
  'field [aria-invalid="true"]': {
    'borderColor': 'var(--danger)'
  },
  'field [aria-invalid="true"]:focus': {
    'boxShadow': [{ 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 3 }, { 'unit': 'string', 'value': 'rgb(229 72 77 / 0.15)' }]
  },
  // ---------- Password field ----------
  'password-field': {
    'position': 'relative'
  },
  'password-field input': {
    'paddingRight': [{ 'unit': 'rem', 'value': 2.75 }]
  },
  'password-toggle': {
    'position': 'absolute',
    'top': [{ 'unit': 'px', 'value': 0 }],
    'right': [{ 'unit': 'px', 'value': 0 }],
    'bottom': [{ 'unit': 'px', 'value': 0 }],
    'width': [{ 'unit': 'rem', 'value': 2.75 }],
    'display': 'grid',
    'placeItems': 'center',
    'background': 'none',
    'border': [{ 'unit': 'string', 'value': 'none' }],
    'color': 'var(--text-muted)',
    'cursor': 'pointer',
    'borderRadius': '0 var(--radius) var(--radius) 0',
    'transition': 'color 0.15s ease'
  },
  'password-toggle:hover': {
    'color': 'var(--text)'
  },
  'password-toggle:focus-visible': {
    'outline': '2px solid var(--accent)',
    'outlineOffset': '-2px'
  },
  // ---------- One-time code entry ----------
  'code-input': {
    'display': 'flex',
    'gap': 'var(--space-2)'
  },
  'code-digit': {
    'width': [{ 'unit': '%H', 'value': 1 }],
    'aspectRatio': '1',
    'padding': [{ 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }],
    'textAlign': 'center',
    'fontSize': [{ 'unit': 'rem', 'value': 1.25 }],
    'fontWeight': '600',
    'fontVariantNumeric': 'tabular-nums'
  },
  'code-fallback': {
    'letterSpacing': [{ 'unit': 'em', 'value': 0.3 }],
    'fontVariantNumeric': 'tabular-nums',
    'textAlign': 'center'
  },
  'auth-resend': {
    'marginTop': [{ 'unit': 'string', 'value': 'var(--space-2)' }],
    'paddingTop': [{ 'unit': 'string', 'value': 'var(--space-4)' }],
    'borderTop': [{ 'unit': 'px', 'value': 1 }, { 'unit': 'string', 'value': 'solid' }, { 'unit': 'string', 'value': 'var(--border)' }]
  },
  'auth-resend-message': {
    'margin': [{ 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }, { 'unit': 'string', 'value': 'var(--space-3)' }, { 'unit': 'px', 'value': 0 }],
    'color': 'var(--success)',
    'fontSize': [{ 'unit': 'rem', 'value': 0.875 }],
    'textAlign': 'center'
  },
  'field-error': {
    'margin': [{ 'unit': 'string', 'value': 'var(--space-1)' }, { 'unit': 'string', 'value': 'var(--space-1)' }, { 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }],
    'color': 'var(--danger)',
    'fontSize': [{ 'unit': 'rem', 'value': 0.8125 }]
  },
  'field-hint': {
    'margin': [{ 'unit': 'string', 'value': 'var(--space-1)' }, { 'unit': 'string', 'value': 'var(--space-1)' }, { 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }],
    'color': 'var(--text-muted)',
    'fontSize': [{ 'unit': 'rem', 'value': 0.8125 }]
  },
  // ---------- Feedback ----------
  'alert': {
    'padding': [{ 'unit': 'string', 'value': 'var(--space-3)' }, { 'unit': 'string', 'value': 'var(--space-3)' }, { 'unit': 'string', 'value': 'var(--space-3)' }, { 'unit': 'string', 'value': 'var(--space-3)' }],
    'borderRadius': 'var(--radius)',
    'border': [{ 'unit': 'px', 'value': 1 }, { 'unit': 'string', 'value': 'solid' }],
    'marginBottom': [{ 'unit': 'string', 'value': 'var(--space-4)' }],
    'fontSize': [{ 'unit': 'rem', 'value': 0.875 }]
  },
  'alert-error': {
    'background': 'rgb(229 72 77 / 0.1)',
    'borderColor': 'var(--danger)',
    'color': '#ffb3b5'
  },
  'alert-success': {
    'background': 'rgb(61 214 140 / 0.1)',
    'borderColor': 'var(--success)',
    'color': '#9ef0c4'
  },
  'alert-info': {
    'background': 'var(--surface-raised)',
    'borderColor': 'var(--border)'
  },
  'empty-state': {
    'padding': [{ 'unit': 'string', 'value': 'var(--space-8)' }, { 'unit': 'string', 'value': 'var(--space-8)' }, { 'unit': 'string', 'value': 'var(--space-8)' }, { 'unit': 'string', 'value': 'var(--space-8)' }],
    'textAlign': 'center',
    'border': [{ 'unit': 'px', 'value': 1 }, { 'unit': 'string', 'value': 'dashed' }, { 'unit': 'string', 'value': 'var(--border)' }],
    'borderRadius': 'var(--radius)',
    'color': 'var(--text-muted)'
  },
  'empty-state h2': {
    'color': 'var(--text)'
  },
  'skeleton-list': {
    'display': 'grid',
    'gap': 'var(--space-3)'
  },
  'skeleton-row': {
    'height': [{ 'unit': 'px', 'value': 72 }],
    'borderRadius': 'var(--radius)',
    'background': 'linear-gradient(90deg, var(--surface), var(--surface-raised), var(--surface))',
    'backgroundSize': '200% 100%',
    'animation': 'shimmer 1.4s ease-in-out infinite'
  },
  'loading-state': {
    'display': 'flex',
    'alignItems': 'center',
    'gap': 'var(--space-2)',
    'color': 'var(--text-muted)',
    'padding': [{ 'unit': 'string', 'value': 'var(--space-4)' }, { 'unit': 'string', 'value': 'var(--space-4)' }, { 'unit': 'string', 'value': 'var(--space-4)' }, { 'unit': 'string', 'value': 'var(--space-4)' }]
  },
  'badge': {
    'display': 'inline-flex',
    'alignItems': 'center',
    'gap': '0.35em',
    'padding': [{ 'unit': 'px', 'value': 2 }, { 'unit': 'string', 'value': 'var(--space-2)' }, { 'unit': 'px', 'value': 2 }, { 'unit': 'string', 'value': 'var(--space-2)' }],
    'borderRadius': '999px',
    'fontSize': [{ 'unit': 'rem', 'value': 0.75 }],
    'fontWeight': '500',
    'border': [{ 'unit': 'px', 'value': 1 }, { 'unit': 'string', 'value': 'solid' }, { 'unit': 'string', 'value': 'var(--border)' }],
    'background': 'var(--surface-raised)',
    'color': 'var(--text-muted)'
  },
  'badge::before': {
    'content': '""',
    'width': [{ 'unit': 'em', 'value': 0.4 }],
    'height': [{ 'unit': 'em', 'value': 0.4 }],
    'borderRadius': '50%',
    'background': 'currentColor'
  },
  'badge-draft': {
    'color': 'var(--accent)',
    'borderColor': 'var(--accent)'
  },
  'badge-archived': {
    'color': 'var(--text-muted)'
  },
  // ---------- Layouts ----------
  'auth-layout': {
    'minHeight': [{ 'unit': 'vh', 'value': 100 }],
    'display': 'grid',
    'placeItems': 'center',
    'padding': [{ 'unit': 'string', 'value': 'var(--space-4)' }, { 'unit': 'string', 'value': 'var(--space-4)' }, { 'unit': 'string', 'value': 'var(--space-4)' }, { 'unit': 'string', 'value': 'var(--space-4)' }],
    'background': 'radial-gradient(60rem 40rem at 50% -10%, rgb(79 124 255 / 0.16), transparent 60%),
    var(--bg)'
  },
  'auth-card': {
    'width': [{ 'unit': '%H', 'value': 1 }],
    'maxWidth': [{ 'unit': 'rem', 'value': 24 }],
    'background': 'var(--surface)',
    'border': [{ 'unit': 'px', 'value': 1 }, { 'unit': 'string', 'value': 'solid' }, { 'unit': 'string', 'value': 'var(--border)' }],
    'borderRadius': 'var(--radius-lg)',
    'padding': [{ 'unit': 'string', 'value': 'var(--space-8)' }, { 'unit': 'string', 'value': 'var(--space-8)' }, { 'unit': 'string', 'value': 'var(--space-6)' }, { 'unit': 'string', 'value': 'var(--space-8)' }],
    'boxShadow': [{ 'unit': 'string', 'value': 'var(--shadow-raised)' }, { 'unit': 'string', 'value': 'var(--shadow-raised)' }, { 'unit': 'string', 'value': 'var(--shadow-raised)' }, { 'unit': 'string', 'value': 'var(--shadow-raised)' }]
  },
  'auth-mark': {
    'display': 'inline-flex',
    'marginBottom': [{ 'unit': 'string', 'value': 'var(--space-4)' }],
    'color': 'var(--accent)'
  },
  'auth-mark-bg': {
    'fill': 'var(--accent-soft)',
    'stroke': 'var(--border)'
  },
  'auth-card h1': {
    'fontSize': [{ 'unit': 'rem', 'value': 1.375 }]
  },
  'auth-subtitle': {
    'marginBottom': [{ 'unit': 'string', 'value': 'var(--space-6)' }],
    'color': 'var(--text-muted)',
    'fontSize': [{ 'unit': 'rem', 'value': 0.875 }]
  },
  'auth-switch': {
    'margin': [{ 'unit': 'string', 'value': 'var(--space-4)' }, { 'unit': 'string', 'value': 'var(--space-4)' }, { 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }],
    'fontSize': [{ 'unit': 'rem', 'value': 0.875 }],
    'color': 'var(--text-muted)',
    'textAlign': 'center'
  },
  'app-shell': {
    'minHeight': [{ 'unit': 'vh', 'value': 100 }],
    'display': 'flex',
    'flexDirection': 'column'
  },
  'app-header': {
    'display': 'flex',
    'alignItems': 'center',
    'justifyContent': 'space-between',
    'gap': 'var(--space-4)',
    'padding': [{ 'unit': 'string', 'value': 'var(--space-3)' }, { 'unit': 'string', 'value': 'var(--space-3)' }, { 'unit': 'string', 'value': 'var(--space-6)' }, { 'unit': 'string', 'value': 'var(--space-3)' }],
    'borderBottom': [{ 'unit': 'px', 'value': 1 }, { 'unit': 'string', 'value': 'solid' }, { 'unit': 'string', 'value': 'var(--border)' }],
    'background': 'var(--surface)',
    'position': 'sticky',
    'top': [{ 'unit': 'px', 'value': 0 }],
    'zIndex': '10'
  },
  'app-brand': {
    'fontWeight': '600',
    'color': 'var(--text)',
    'letterSpacing': [{ 'unit': 'em', 'value': -0.01 }]
  },
  'app-user': {
    'display': 'flex',
    'alignItems': 'center',
    'gap': 'var(--space-3)',
    'fontSize': [{ 'unit': 'rem', 'value': 0.875 }],
    'color': 'var(--text-muted)'
  },
  'app-main': {
    'flex': '1',
    'padding': [{ 'unit': 'string', 'value': 'var(--space-6)' }, { 'unit': 'string', 'value': 'var(--space-6)' }, { 'unit': 'string', 'value': 'var(--space-6)' }, { 'unit': 'string', 'value': 'var(--space-6)' }],
    'maxWidth': [{ 'unit': 'rem', 'value': 72 }],
    'width': [{ 'unit': '%H', 'value': 1 }],
    'margin': [{ 'unit': 'px', 'value': 0 }, { 'unit': 'string', 'value': 'auto' }, { 'unit': 'px', 'value': 0 }, { 'unit': 'string', 'value': 'auto' }]
  },
  'projects-page': {
    'display': 'grid',
    'gridTemplateColumns': '1fr',
    'gap': 'var(--space-6)',
    '>w60': {
      'gridTemplateColumns': '1fr 22rem'
    }
  },
  'panel': {
    'background': 'var(--surface)',
    'border': [{ 'unit': 'px', 'value': 1 }, { 'unit': 'string', 'value': 'solid' }, { 'unit': 'string', 'value': 'var(--border)' }],
    'borderRadius': 'var(--radius-lg)',
    'padding': [{ 'unit': 'string', 'value': 'var(--space-4)' }, { 'unit': 'string', 'value': 'var(--space-4)' }, { 'unit': 'string', 'value': 'var(--space-4)' }, { 'unit': 'string', 'value': 'var(--space-4)' }],
    'boxShadow': [{ 'unit': 'string', 'value': 'var(--shadow-card)' }, { 'unit': 'string', 'value': 'var(--shadow-card)' }, { 'unit': 'string', 'value': 'var(--shadow-card)' }, { 'unit': 'string', 'value': 'var(--shadow-card)' }]
  },
  'project-list': {
    'listStyle': 'none',
    'margin': [{ 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }],
    'padding': [{ 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }],
    'display': 'grid',
    'gap': 'var(--space-3)'
  },
  'project-card': {
    'background': 'var(--surface)',
    'border': [{ 'unit': 'px', 'value': 1 }, { 'unit': 'string', 'value': 'solid' }, { 'unit': 'string', 'value': 'var(--border)' }],
    'borderRadius': 'var(--radius-lg)',
    'padding': [{ 'unit': 'string', 'value': 'var(--space-4)' }, { 'unit': 'string', 'value': 'var(--space-4)' }, { 'unit': 'string', 'value': 'var(--space-4)' }, { 'unit': 'string', 'value': 'var(--space-4)' }],
    'boxShadow': [{ 'unit': 'string', 'value': 'var(--shadow-card)' }, { 'unit': 'string', 'value': 'var(--shadow-card)' }, { 'unit': 'string', 'value': 'var(--shadow-card)' }, { 'unit': 'string', 'value': 'var(--shadow-card)' }],
    'transition': 'border-color 0.15s ease, transform 0.15s ease'
  },
  'project-card:hover': {
    'borderColor': 'var(--accent)',
    'transform': 'translateY(-1px)'
  },
  'project-card-header': {
    'display': 'flex',
    'alignItems': 'center',
    'justifyContent': 'space-between',
    'gap': 'var(--space-3)'
  },
  'project-description': {
    'margin': [{ 'unit': 'string', 'value': 'var(--space-2)' }, { 'unit': 'string', 'value': 'var(--space-2)' }, { 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }],
    'color': 'var(--text-muted)',
    'fontSize': [{ 'unit': 'rem', 'value': 0.875 }]
  },
  'project-meta': {
    'margin': [{ 'unit': 'string', 'value': 'var(--space-2)' }, { 'unit': 'string', 'value': 'var(--space-2)' }, { 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }],
    'fontSize': [{ 'unit': 'rem', 'value': 0.8125 }],
    'color': 'var(--text-muted)'
  },
  'project-slug': {
    'fontFamily': 'var(--font-mono)'
  },
  'pagination': {
    'display': 'flex',
    'alignItems': 'center',
    'justifyContent': 'center',
    'gap': 'var(--space-4)',
    'marginTop': [{ 'unit': 'string', 'value': 'var(--space-6)' }],
    'fontSize': [{ 'unit': 'rem', 'value': 0.875 }],
    'color': 'var(--text-muted)'
  },
  'pagination-disabled': {
    'opacity': '0.4'
  },
  'project-detail': {
    'maxWidth': [{ 'unit': 'rem', 'value': 48 }]
  },
  'breadcrumb': {
    'marginBottom': [{ 'unit': 'string', 'value': 'var(--space-4)' }],
    'fontSize': [{ 'unit': 'rem', 'value': 0.875 }]
  },
  'project-detail-header': {
    'display': 'flex',
    'alignItems': 'center',
    'gap': 'var(--space-3)'
  },
  'project-facts': {
    'display': 'grid',
    'gap': 'var(--space-3)',
    'margin': [{ 'unit': 'string', 'value': 'var(--space-6)' }, { 'unit': 'string', 'value': 'var(--space-6)' }, { 'unit': 'px', 'value': 0 }, { 'unit': 'string', 'value': 'var(--space-6)' }],
    'padding': [{ 'unit': 'string', 'value': 'var(--space-4)' }, { 'unit': 'string', 'value': 'var(--space-4)' }, { 'unit': 'string', 'value': 'var(--space-4)' }, { 'unit': 'string', 'value': 'var(--space-4)' }],
    'background': 'var(--surface)',
    'border': [{ 'unit': 'px', 'value': 1 }, { 'unit': 'string', 'value': 'solid' }, { 'unit': 'string', 'value': 'var(--border)' }],
    'borderRadius': 'var(--radius)',
    '>w40': {
      'gridTemplateColumns': 'repeat(3, 1fr)'
    }
  },
  'project-facts dt': {
    'fontSize': [{ 'unit': 'rem', 'value': 0.75 }],
    'textTransform': 'uppercase',
    'letterSpacing': [{ 'unit': 'em', 'value': 0.04 }],
    'color': 'var(--text-muted)'
  },
  'project-facts dd': {
    'margin': [{ 'unit': 'string', 'value': 'var(--space-1)' }, { 'unit': 'string', 'value': 'var(--space-1)' }, { 'unit': 'px', 'value': 0 }, { 'unit': 'px', 'value': 0 }],
    'fontSize': [{ 'unit': 'rem', 'value': 0.875 }]
  },
  'project-actions': {
    'display': 'flex',
    'flexWrap': 'wrap',
    'alignItems': 'center',
    'gap': 'var(--space-3)',
    'paddingTop': [{ 'unit': 'string', 'value': 'var(--space-4)' }],
    'borderTop': [{ 'unit': 'px', 'value': 1 }, { 'unit': 'string', 'value': 'solid' }, { 'unit': 'string', 'value': 'var(--border)' }]
  },
  'confirm-row': {
    'display': 'flex',
    'flexWrap': 'wrap',
    'alignItems': 'center',
    'gap': 'var(--space-2)',
    'fontSize': [{ 'unit': 'rem', 'value': 0.875 }]
  },
  'error-page': {
    'maxWidth': [{ 'unit': 'rem', 'value': 32 }],
    'margin': [{ 'unit': 'string', 'value': 'var(--space-8)' }, { 'unit': 'string', 'value': 'var(--space-8)' }, { 'unit': 'string', 'value': 'auto' }, { 'unit': 'string', 'value': 'var(--space-8)' }],
    'padding': [{ 'unit': 'string', 'value': 'var(--space-4)' }, { 'unit': 'string', 'value': 'var(--space-4)' }, { 'unit': 'string', 'value': 'var(--space-4)' }, { 'unit': 'string', 'value': 'var(--space-4)' }],
    'textAlign': 'center'
  },
  'error-actions': {
    'display': 'flex',
    'alignItems': 'center',
    'justifyContent': 'center',
    'gap': 'var(--space-4)'
  }
});
