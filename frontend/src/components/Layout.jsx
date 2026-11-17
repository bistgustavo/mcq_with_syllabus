import { useEffect, useState } from 'react'
import { Link, NavLink, Navigate, Outlet, useLocation } from 'react-router-dom'
import {
  Activity,
  BookOpenText,
  ClipboardCheck,
  GraduationCap,
  History,
  LayoutDashboard,
  Library,
  LogOut,
  Menu,
  Palette,
  Users,
  X,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useBranding } from '../context/BrandingContext'
import { Spinner, cx } from './ui'

export function Logo({ size = 'md', inverted = false, to = '/' }) {
  const { branding } = useBranding()
  const initials = branding.institution_name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase()
  const box = size === 'lg' ? 'h-11 w-11 text-base' : 'h-9 w-9 text-sm'
  return (
    <Link to={to} className="flex min-w-0 items-center gap-2.5">
      {branding.logo_url ? (
        <img src={branding.logo_url} alt="" className={cx(box, 'rounded-xl object-contain')} />
      ) : (
        <span className={cx(box, 'grid shrink-0 place-items-center rounded-xl bg-brand-600 font-bold text-white shadow-sm')}>
          {initials || 'Q'}
        </span>
      )}
      <span className={cx('truncate font-bold tracking-tight', inverted ? 'text-white' : 'text-ink-900', size === 'lg' && 'text-lg')}>
        {branding.institution_name}
      </span>
    </Link>
  )
}

const LEARN = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/courses', label: 'Courses & syllabus', icon: BookOpenText },
  { to: '/mock-tests', label: 'Mock tests', icon: ClipboardCheck },
  { to: '/history', label: 'My results', icon: History },
]
const ADMIN = [
  { to: '/admin', label: 'Overview', icon: Activity, end: true },
  { to: '/admin/courses', label: 'Courses & content', icon: Library },
  { to: '/admin/users', label: 'Students & staff', icon: Users },
  { to: '/admin/settings', label: 'Branding & settings', icon: Palette },
]

function NavGroup({ title, items, onNavigate }) {
  return (
    <div>
      <p className="mb-2 px-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-400">{title}</p>
      <div className="space-y-0.5">
        {items.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            onClick={onNavigate}
            className={({ isActive }) =>
              cx(
                'group flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition',
                isActive ? 'bg-brand-50 text-brand-700' : 'text-ink-600 hover:bg-ink-100 hover:text-ink-900',
              )
            }
          >
            {({ isActive }) => (
              <>
                <Icon className={cx('h-[18px] w-[18px]', isActive ? 'text-brand-600' : 'text-ink-400 group-hover:text-ink-600')} />
                {label}
              </>
            )}
          </NavLink>
        ))}
      </div>
    </div>
  )
}

function Sidebar({ onNavigate }) {
  const { user, isAdmin, logout } = useAuth()
  const name = user?.full_name || user?.email || ''
  return (
    <div className="flex h-full flex-col">
      <div className="px-5 pb-6 pt-5">
        <Logo to="/dashboard" />
      </div>
      <nav className="flex-1 space-y-7 overflow-y-auto px-3">
        <NavGroup title="Learn" items={LEARN} onNavigate={onNavigate} />
        {isAdmin && <NavGroup title="Administration" items={ADMIN} onNavigate={onNavigate} />}
      </nav>
      <div className="m-3 rounded-2xl border border-ink-200 bg-ink-50 p-3">
        <div className="flex items-center gap-3">
          <Link to="/profile" onClick={onNavigate} className="flex min-w-0 flex-1 items-center gap-3">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-gradient-to-br from-brand-500 to-brand-700 text-sm font-bold text-white">
              {name.slice(0, 1).toUpperCase()}
            </span>
            <span className="min-w-0">
              <span className="block truncate text-sm font-semibold text-ink-900">{user?.full_name || 'My account'}</span>
              <span className="block truncate text-xs text-ink-500">{isAdmin ? 'Administrator' : user?.email}</span>
            </span>
          </Link>
          <button onClick={logout} className="rounded-lg p-2 text-ink-400 hover:bg-white hover:text-ink-700" title="Sign out">
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  )
}

export function AppLayout() {
  const [open, setOpen] = useState(false)
  const location = useLocation()
  useEffect(() => setOpen(false), [location.pathname])

  return (
    <div className="min-h-screen lg:pl-64">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-ink-200 bg-white lg:block">
        <Sidebar />
      </aside>

      <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-ink-200 bg-white/90 px-4 backdrop-blur lg:hidden">
        <button onClick={() => setOpen(true)} className="rounded-lg p-2 text-ink-600 hover:bg-ink-100" aria-label="Open menu">
          <Menu className="h-5 w-5" />
        </button>
        <Logo to="/dashboard" />
      </header>

      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-ink-950/40" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-72 animate-fade-up bg-white shadow-lift">
            <button onClick={() => setOpen(false)} className="absolute right-3 top-4 rounded-lg p-1.5 text-ink-400 hover:bg-ink-100" aria-label="Close menu">
              <X className="h-5 w-5" />
            </button>
            <Sidebar onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      )}

      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-10 lg:py-10">
        <div key={location.pathname} className="animate-fade-up">
          <Outlet />
        </div>
      </main>
    </div>
  )
}

export function RequireAuth({ children, admin = false }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <Spinner label="Checking your session…" className="min-h-screen" />
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (admin && !user.is_admin) return <Navigate to="/dashboard" replace />
  return children
}

export function GraduationMark(props) {
  return <GraduationCap {...props} />
}
