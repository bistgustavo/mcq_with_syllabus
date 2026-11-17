import { useEffect } from 'react'
import { AlertTriangle, Loader2, X } from 'lucide-react'

export const cx = (...c) => c.filter(Boolean).join(' ')

// --------------------------------------------------------------------------- buttons
const VARIANTS = {
  primary: 'bg-brand-600 text-white shadow-sm hover:bg-brand-700 focus-visible:ring-brand-500',
  accent: 'bg-accent-600 text-white shadow-sm hover:bg-accent-700 focus-visible:ring-accent-500',
  secondary: 'bg-white text-ink-700 ring-1 ring-inset ring-ink-200 shadow-sm hover:bg-ink-50 hover:ring-ink-300',
  soft: 'bg-brand-50 text-brand-700 hover:bg-brand-100',
  danger: 'bg-rose-600 text-white shadow-sm hover:bg-rose-700 focus-visible:ring-rose-500',
  ghost: 'text-ink-600 hover:bg-ink-100 hover:text-ink-900',
  dark: 'bg-ink-900 text-white hover:bg-ink-800',
}
const SIZES = {
  xs: 'h-7 px-2.5 text-xs gap-1.5',
  sm: 'h-8 px-3 text-sm gap-1.5',
  md: 'h-10 px-4 text-sm gap-2',
  lg: 'h-12 px-6 text-base gap-2',
}

export function Button({ variant = 'primary', size = 'md', loading, className, children, disabled, ...props }) {
  return (
    <button
      className={cx(
        'inline-flex shrink-0 items-center justify-center rounded-xl font-semibold transition-all duration-150',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 active:scale-[.98]',
        'disabled:pointer-events-none disabled:opacity-50',
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  )
}

// --------------------------------------------------------------------------- surfaces
export function Card({ className, children, as: Tag = 'div', ...props }) {
  return (
    <Tag className={cx('rounded-2xl border border-ink-200/80 bg-white shadow-card', className)} {...props}>
      {children}
    </Tag>
  )
}

export function CardHeader({ title, subtitle, icon: Icon, actions, className }) {
  return (
    <div className={cx('flex items-start gap-3 border-b border-ink-100 px-5 py-4', className)}>
      {Icon && (
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-600">
          <Icon className="h-[18px] w-[18px]" />
        </div>
      )}
      <div className="min-w-0 flex-1">
        <h2 className="font-semibold text-ink-900">{title}</h2>
        {subtitle && <p className="mt-0.5 text-sm text-ink-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  )
}

export function PageHeader({ title, subtitle, actions, eyebrow, breadcrumb }) {
  return (
    <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {breadcrumb && <div className="mb-2 text-sm text-ink-500">{breadcrumb}</div>}
        {eyebrow && <p className="eyebrow mb-1.5">{eyebrow}</p>}
        <h1 className="text-2xl font-bold tracking-tight text-ink-900 sm:text-[28px]">{title}</h1>
        {subtitle && <p className="mt-1.5 max-w-2xl text-[15px] text-ink-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  )
}

// --------------------------------------------------------------------------- feedback
export function Spinner({ label = 'Loading…', className }) {
  return (
    <div className={cx('flex items-center justify-center gap-2 py-16 text-ink-500', className)}>
      <Loader2 className="h-5 w-5 animate-spin text-brand-600" /> <span className="text-sm">{label}</span>
    </div>
  )
}

export function Skeleton({ className }) {
  return <div className={cx('animate-pulse rounded-xl bg-ink-100', className)} />
}

export function ErrorBox({ error, onRetry }) {
  if (!error) return null
  return (
    <div className="mb-4 flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="flex-1">{error.message || String(error)}</div>
      {onRetry && (
        <button onClick={() => onRetry()} className="font-semibold underline-offset-2 hover:underline">
          Retry
        </button>
      )}
    </div>
  )
}

export function Notice({ tone = 'info', icon: Icon, title, children, className }) {
  const tones = {
    info: 'border-brand-200 bg-brand-50 text-brand-900',
    warn: 'border-amber-200 bg-amber-50 text-amber-900',
    success: 'border-emerald-200 bg-emerald-50 text-emerald-900',
  }
  return (
    <div className={cx('flex gap-3 rounded-xl border px-4 py-3 text-sm', tones[tone], className)}>
      {Icon && <Icon className="mt-0.5 h-4 w-4 shrink-0" />}
      <div>
        {title && <p className="font-semibold">{title}</p>}
        <div className={title ? 'mt-0.5 opacity-90' : ''}>{children}</div>
      </div>
    </div>
  )
}

export function EmptyState({ icon: Icon, title, children, action, className }) {
  return (
    <div className={cx('flex flex-col items-center rounded-2xl border border-dashed border-ink-300 bg-white/60 px-6 py-14 text-center', className)}>
      {Icon && (
        <div className="mb-4 grid h-12 w-12 place-items-center rounded-2xl bg-brand-50 text-brand-600">
          <Icon className="h-6 w-6" />
        </div>
      )}
      <h3 className="font-semibold text-ink-900">{title}</h3>
      {children && <p className="mt-1.5 max-w-md text-sm text-ink-500">{children}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

// --------------------------------------------------------------------------- badges & stats
const BADGE = {
  slate: 'bg-ink-100 text-ink-700 ring-ink-200',
  green: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  amber: 'bg-amber-50 text-amber-700 ring-amber-200',
  red: 'bg-rose-50 text-rose-700 ring-rose-200',
  blue: 'bg-brand-50 text-brand-700 ring-brand-200',
  violet: 'bg-violet-50 text-violet-700 ring-violet-200',
}

export function Badge({ tone = 'slate', children, className }) {
  return (
    <span className={cx('inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ring-inset', BADGE[tone], className)}>
      {children}
    </span>
  )
}

export function DifficultyBadge({ value }) {
  const tone = { easy: 'green', medium: 'amber', hard: 'red' }[value] || 'slate'
  return <Badge tone={tone}>{value ? value[0].toUpperCase() + value.slice(1) : 'Mixed'}</Badge>
}

export function StatusBadge({ status }) {
  const map = {
    ready: ['green', 'Ready'],
    pending: ['blue', 'Queued'],
    processing: ['violet', 'Processing'],
    failed: ['red', 'Failed'],
    empty: ['amber', 'No text'],
  }
  const [tone, label] = map[status] || ['slate', status]
  return (
    <Badge tone={tone}>
      {(status === 'pending' || status === 'processing') && <Loader2 className="h-3 w-3 animate-spin" />}
      {label}
    </Badge>
  )
}

export function Stat({ label, value, hint, icon: Icon, tone = 'brand' }) {
  const tones = {
    brand: 'bg-brand-50 text-brand-600',
    green: 'bg-emerald-50 text-emerald-600',
    amber: 'bg-amber-50 text-amber-600',
    violet: 'bg-violet-50 text-violet-600',
    accent: 'bg-accent-50 text-accent-600',
  }
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-ink-500">{label}</p>
        {Icon && (
          <div className={cx('grid h-9 w-9 place-items-center rounded-xl', tones[tone])}>
            <Icon className="h-[18px] w-[18px]" />
          </div>
        )}
      </div>
      <p className="num mt-2 text-[28px] font-bold leading-none tracking-tight text-ink-900">{value}</p>
      {hint && <p className="mt-2 text-xs text-ink-500">{hint}</p>}
    </Card>
  )
}
export const StatCard = Stat

export function ProgressBar({ value, className, tone }) {
  const pct = Math.max(0, Math.min(100, value || 0))
  const color = tone || (pct >= 75 ? 'bg-emerald-500' : pct >= 45 ? 'bg-amber-500' : 'bg-rose-500')
  return (
    <div className={cx('h-2 w-full overflow-hidden rounded-full bg-ink-100', className)}>
      <div className={cx('h-full rounded-full transition-all duration-500', color)} style={{ width: `${pct}%` }} />
    </div>
  )
}

export function Ring({ value, size = 120, stroke = 10, label, sub, tone }) {
  const pct = Math.max(0, Math.min(100, value || 0))
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const color = tone || (pct >= 75 ? '#10b981' : pct >= 45 ? '#f59e0b' : '#f43f5e')
  return (
    <div className="relative grid place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} stroke="#e2e8f0" strokeWidth={stroke} fill="none" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke={color}
          strokeWidth={stroke}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c - (pct / 100) * c}
          style={{ transition: 'stroke-dashoffset .8s ease' }}
        />
      </svg>
      <div className="absolute text-center">
        <p className="num text-2xl font-bold text-ink-900">{label ?? `${Math.round(pct)}%`}</p>
        {sub && <p className="text-xs text-ink-500">{sub}</p>}
      </div>
    </div>
  )
}

// --------------------------------------------------------------------------- forms
export function Field({ label, hint, error, children, className }) {
  return (
    <label className={cx('block', className)}>
      {label && <span className="mb-1.5 block text-sm font-medium text-ink-700">{label}</span>}
      {children}
      {hint && !error && <span className="mt-1.5 block text-xs text-ink-500">{hint}</span>}
      {error && <span className="mt-1.5 block text-xs text-rose-600">{error}</span>}
    </label>
  )
}

const inputClass =
  'block w-full rounded-xl border-0 bg-white px-3.5 py-2.5 text-sm text-ink-900 shadow-sm ring-1 ring-inset ring-ink-200 ' +
  'placeholder:text-ink-400 transition focus:ring-2 focus:ring-inset focus:ring-brand-500 disabled:bg-ink-50 disabled:text-ink-500'

export const Input = (props) => <input className={inputClass} {...props} />
export const Textarea = ({ className, ...props }) => <textarea className={cx(inputClass, className)} rows={3} {...props} />
export function Select({ children, ...props }) {
  return (
    <select className={cx(inputClass, 'pr-9')} {...props}>
      {children}
    </select>
  )
}

export function Toggle({ checked, onChange, label, description }) {
  return (
    <label className="flex cursor-pointer items-start gap-3">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={cx(
          'relative mt-0.5 inline-flex h-6 w-11 shrink-0 rounded-full transition-colors',
          checked ? 'bg-brand-600' : 'bg-ink-200',
        )}
      >
        <span className={cx('absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all', checked ? 'left-[22px]' : 'left-0.5')} />
      </button>
      <span>
        <span className="block text-sm font-medium text-ink-800">{label}</span>
        {description && <span className="block text-xs text-ink-500">{description}</span>}
      </span>
    </label>
  )
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="mb-6 flex gap-1 overflow-x-auto rounded-xl bg-ink-100 p-1">
      {tabs.map((t) => (
        <button
          key={t.value}
          onClick={() => onChange(t.value)}
          className={cx(
            'flex items-center gap-2 whitespace-nowrap rounded-lg px-3.5 py-2 text-sm font-semibold transition',
            value === t.value ? 'bg-white text-ink-900 shadow-sm' : 'text-ink-500 hover:text-ink-800',
          )}
        >
          {t.icon && <t.icon className="h-4 w-4" />}
          {t.label}
          {t.count !== undefined && <span className="rounded-full bg-ink-200/70 px-1.5 text-xs">{t.count}</span>}
        </button>
      ))}
    </div>
  )
}

// --------------------------------------------------------------------------- overlays
export function Modal({ open, onClose, title, children, footer, wide }) {
  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => e.key === 'Escape' && onClose?.()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink-950/40 p-4 backdrop-blur-[2px] sm:items-center" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        className={cx('w-full animate-fade-up rounded-2xl bg-white shadow-lift', wide ? 'max-w-2xl' : 'max-w-md')}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 pt-5">
          <h2 className="text-lg font-semibold text-ink-900">{title}</h2>
          <button onClick={onClose} className="rounded-lg p-1 text-ink-400 hover:bg-ink-100 hover:text-ink-700" aria-label="Close">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="max-h-[70vh] overflow-y-auto px-6 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-ink-100 px-6 py-4">{footer}</div>}
      </div>
    </div>
  )
}

export function ConfirmModal({ open, title, message, confirmLabel = 'Delete', variant = 'danger', onConfirm, onClose, loading }) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button variant={variant} onClick={onConfirm} loading={loading}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="text-sm leading-relaxed text-ink-600">{message}</div>
    </Modal>
  )
}
