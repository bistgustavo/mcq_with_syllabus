import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'

const DEFAULT = {
  institution_name: 'QuizForge',
  tagline: 'Exam preparation, built from your syllabus',
  primary_color: '#1d4ed8',
  accent_color: '#e11d48',
  logo_url: null,
  support_email: null,
  allow_signup: true,
}

const BrandingContext = createContext({ branding: DEFAULT, setBranding: () => {} })

function hexToRgb(hex) {
  const n = parseInt(hex.replace('#', ''), 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

function mix(a, b, t) {
  return a.map((v, i) => Math.round(v + (b[i] - v) * t))
}

/** Build an 11-step palette (50…950) around ``hex`` (treated as the 600 shade). */
export function palette(hex) {
  const base = hexToRgb(hex)
  const white = [255, 255, 255]
  const black = [2, 6, 23]
  return {
    50: mix(base, white, 0.94), 100: mix(base, white, 0.87), 200: mix(base, white, 0.74), 300: mix(base, white, 0.56),
    400: mix(base, white, 0.34), 500: mix(base, white, 0.14), 600: base, 700: mix(base, black, 0.16),
    800: mix(base, black, 0.32), 900: mix(base, black, 0.46), 950: mix(base, black, 0.64),
  }
}

export function applyColors(primary, accent) {
  const root = document.documentElement
  for (const [name, hex] of [['brand', primary], ['accent', accent]]) {
    if (!/^#[0-9a-f]{6}$/i.test(hex || '')) continue
    Object.entries(palette(hex)).forEach(([step, rgb]) => root.style.setProperty(`--${name}-${step}`, rgb.join(' ')))
  }
}

export function BrandingProvider({ children }) {
  const [branding, setState] = useState(() => {
    try {
      return { ...DEFAULT, ...JSON.parse(localStorage.getItem('branding') || '{}') }
    } catch {
      return DEFAULT
    }
  })

  const setBranding = useCallback((b) => {
    const next = { ...DEFAULT, ...b }
    setState(next)
    try {
      localStorage.setItem('branding', JSON.stringify(next))
    } catch {
      /* ignore */
    }
  }, [])

  useEffect(() => {
    api.branding().then(setBranding).catch(() => {})
  }, [setBranding])

  useEffect(() => {
    applyColors(branding.primary_color, branding.accent_color)
    document.title = branding.institution_name
  }, [branding])

  const value = useMemo(() => ({ branding, setBranding }), [branding, setBranding])
  return <BrandingContext.Provider value={value}>{children}</BrandingContext.Provider>
}

export const useBranding = () => useContext(BrandingContext)
