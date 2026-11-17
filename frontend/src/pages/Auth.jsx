import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { BarChart3, CheckCircle2, Clock3, Eye, EyeOff } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useBranding } from '../context/BrandingContext'
import { Button, ErrorBox, Field, Input } from '../components/ui'
import { Logo } from '../components/Layout'

function AuthShell({ title, subtitle, children, footer }) {
  const { branding } = useBranding()
  return (
    <div className="grid min-h-screen bg-white lg:grid-cols-[1fr_1.05fr]">
      <div className="flex flex-col px-6 py-8 sm:px-12">
        <Logo />
        <div className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center py-10">
          <h1 className="text-[28px] font-bold tracking-tight text-ink-900">{title}</h1>
          <p className="mb-8 mt-2 text-ink-500">{subtitle}</p>
          {children}
          <div className="mt-8 text-center text-sm text-ink-500">{footer}</div>
        </div>
        <p className="text-xs text-ink-400">© {new Date().getFullYear()} {branding.institution_name}</p>
      </div>

      <div className="relative hidden overflow-hidden bg-brand-700 lg:block">
        <div className="absolute inset-0 bg-[radial-gradient(80%_60%_at_100%_0%,rgb(var(--brand-500))_0%,transparent_60%),radial-gradient(60%_50%_at_0%_100%,rgb(var(--brand-900))_0%,transparent_70%)]" />
        <div className="absolute inset-0 bg-[linear-gradient(to_right,rgb(255_255_255/.06)_1px,transparent_1px),linear-gradient(to_bottom,rgb(255_255_255/.06)_1px,transparent_1px)] bg-[size:40px_40px]" />
        <div className="relative flex h-full flex-col justify-between p-12 text-white">
          <p className="text-sm font-semibold text-brand-100">{branding.institution_name}</p>
          <div>
            <h2 className="max-w-md text-4xl font-bold leading-tight tracking-tight">{branding.tagline}</h2>
            <ul className="mt-10 space-y-5 text-brand-50">
              {[
                [Clock3, 'Timed mock tests that mirror the real paper, negative marking included'],
                [BarChart3, 'Chapter-wise analysis after every test'],
                [CheckCircle2, 'A clear explanation for every single answer'],
              ].map(([Icon, text]) => (
                <li key={text} className="flex items-start gap-3">
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-white/10 ring-1 ring-white/20">
                    <Icon className="h-4 w-4" />
                  </span>
                  <span className="pt-1">{text}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="grid grid-cols-3 gap-3 rounded-2xl bg-white/10 p-5 text-center ring-1 ring-white/15 backdrop-blur">
            {[
              ['Syllabus', 'mapped topic by topic'],
              ['Timed', 'full-length papers'],
              ['Instant', 'results & review'],
            ].map(([big, small]) => (
              <div key={big}>
                <p className="text-lg font-bold">{big}</p>
                <p className="text-xs text-brand-100">{small}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function PasswordInput({ value, onChange, autoComplete, minLength }) {
  const [show, setShow] = useState(false)
  return (
    <div className="relative">
      <Input type={show ? 'text' : 'password'} required autoComplete={autoComplete} minLength={minLength} value={value} onChange={onChange} />
      <button
        type="button"
        onClick={() => setShow((s) => !s)}
        className="absolute inset-y-0 right-0 grid w-10 place-items-center text-ink-400 hover:text-ink-700"
        aria-label={show ? 'Hide password' : 'Show password'}
      >
        {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </div>
  )
}

export function LoginPage() {
  const { user, login } = useAuth()
  const { branding } = useBranding()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const target = location.state?.from && location.state.from !== '/' ? location.state.from : '/dashboard'

  if (user) return <Navigate to={target} replace />

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(email, password)
      navigate(target, { replace: true })
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell
      title="Welcome back"
      subtitle="Sign in to continue your preparation."
      footer={
        branding.allow_signup ? (
          <>
            New here?{' '}
            <Link to="/register" className="font-semibold text-brand-600 hover:underline">
              Create an account
            </Link>
          </>
        ) : (
          'Accounts are provided by your institution.'
        )
      }
    >
      <form onSubmit={submit} className="space-y-5">
        <ErrorBox error={error} />
        <Field label="E-mail address">
          <Input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Password">
          <PasswordInput autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <Button type="submit" size="lg" className="w-full" loading={busy}>
          Sign in
        </Button>
      </form>
    </AuthShell>
  )
}

export function RegisterPage() {
  const { user, register } = useAuth()
  const { branding } = useBranding()
  const navigate = useNavigate()
  const [form, setForm] = useState({ full_name: '', email: '', password: '' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to="/dashboard" replace />
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))
  const strong = form.password.length >= 8 && /[a-z]/i.test(form.password) && /\d/.test(form.password)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const u = await register({ email: form.email, password: form.password, full_name: form.full_name || null })
      navigate(u.is_admin ? '/admin' : '/dashboard', { replace: true })
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell
      title="Create your account"
      subtitle={`Start preparing with ${branding.institution_name}. It takes 30 seconds.`}
      footer={
        <>
          Already registered?{' '}
          <Link to="/login" className="font-semibold text-brand-600 hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      {!branding.allow_signup && (
        <p className="mb-4 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-800">
          Self sign-up is closed. Please ask your institution for an account.
        </p>
      )}
      <form onSubmit={submit} className="space-y-5">
        <ErrorBox error={error} />
        <Field label="Full name">
          <Input autoComplete="name" required value={form.full_name} onChange={set('full_name')} />
        </Field>
        <Field label="E-mail address">
          <Input type="email" autoComplete="email" required value={form.email} onChange={set('email')} />
        </Field>
        <Field
          label="Password"
          hint={
            <span className={strong ? 'text-emerald-600' : ''}>
              {strong ? '✓ Strong enough' : 'At least 8 characters, with letters and numbers'}
            </span>
          }
        >
          <PasswordInput autoComplete="new-password" minLength={8} value={form.password} onChange={set('password')} />
        </Field>
        <Button type="submit" size="lg" className="w-full" loading={busy} disabled={!strong}>
          Create account
        </Button>
      </form>
    </AuthShell>
  )
}
