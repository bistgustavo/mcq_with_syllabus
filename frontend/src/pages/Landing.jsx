import { Link } from 'react-router-dom'
import {
  ArrowRight,
  BarChart3,
  BookOpenCheck,
  CheckCircle2,
  Clock3,
  FileSearch,
  Layers3,
  ShieldCheck,
  Sparkles,
  Target,
} from 'lucide-react'
import { api } from '../api/client'
import { useBranding } from '../context/BrandingContext'
import { useAsync } from '../hooks/useAsync'
import { Logo } from '../components/Layout'
import { Button } from '../components/ui'

const FEATURES = [
  {
    icon: BookOpenCheck,
    title: 'Mapped to the official syllabus',
    body: 'Every chapter and topic of the exam syllabus, with the same weightage the real paper uses.',
  },
  {
    icon: Clock3,
    title: 'Real exam conditions',
    body: 'Full-length timed mock tests with negative marking, a question palette and mark-for-review.',
  },
  {
    icon: BarChart3,
    title: 'Know exactly where you stand',
    body: 'Chapter-wise analysis after every test shows your weak areas so you revise what matters.',
  },
  {
    icon: Sparkles,
    title: 'A question bank that keeps growing',
    body: 'New, non-repeating questions written from study material and verified sources for every topic.',
  },
]

const STEPS = [
  { icon: Layers3, title: 'Pick your exam', body: 'Open the course and see the full syllabus and exam pattern.' },
  { icon: Target, title: 'Practise topic by topic', body: 'Short quizzes with instant explanations for every answer.' },
  { icon: Clock3, title: 'Sit full mock tests', body: 'Timed papers exactly like the real one, with negative marking.' },
  { icon: BarChart3, title: 'Fix weak chapters', body: 'Your results point you to the chapters that need more work.' },
]

export default function Landing() {
  const { branding } = useBranding()
  const { data } = useAsync(() => api.publicStats(), [])
  const courses = data?.courses || []
  const featured = courses[0]

  return (
    <div className="min-h-screen bg-white">
      {/* nav */}
      <header className="sticky top-0 z-30 border-b border-ink-100 bg-white/85 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-4 sm:px-6">
          <Logo />
          <nav className="ml-auto flex items-center gap-2">
            <a href="#courses" className="hidden rounded-lg px-3 py-2 text-sm font-medium text-ink-600 hover:text-ink-900 sm:block">
              Courses
            </a>
            <a href="#how" className="hidden rounded-lg px-3 py-2 text-sm font-medium text-ink-600 hover:text-ink-900 sm:block">
              How it works
            </a>
            <Link to="/login">
              <Button variant="ghost" size="sm">Sign in</Button>
            </Link>
            {branding.allow_signup && (
              <Link to="/register">
                <Button size="sm">Start preparing</Button>
              </Link>
            )}
          </nav>
        </div>
      </header>

      {/* hero */}
      <section className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_60%_at_70%_0%,rgb(var(--brand-100))_0%,transparent_70%)]" />
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,rgb(var(--brand-100)/.5)_1px,transparent_1px),linear-gradient(to_bottom,rgb(var(--brand-100)/.5)_1px,transparent_1px)] bg-[size:48px_48px] [mask-image:radial-gradient(ellipse_at_top,black_30%,transparent_75%)]" />
        <div className="relative mx-auto grid max-w-6xl gap-12 px-4 pb-20 pt-16 sm:px-6 lg:grid-cols-[1.1fr_.9fr] lg:pt-24">
          <div>
            <p className="inline-flex items-center gap-2 rounded-full border border-brand-200 bg-white px-3 py-1 text-xs font-semibold text-brand-700 shadow-sm">
              <span className="h-1.5 w-1.5 rounded-full bg-accent-500" />
              {featured ? `Now preparing: ${featured.name}` : 'Competitive exam preparation'}
            </p>
            <h1 className="mt-6 text-4xl font-extrabold leading-[1.08] tracking-tight text-ink-900 sm:text-5xl lg:text-[56px]">
              Prepare smarter.
              <br />
              <span className="bg-gradient-to-r from-brand-600 to-brand-800 bg-clip-text text-transparent">Walk in exam-ready.</span>
            </h1>
            <p className="mt-6 max-w-xl text-lg leading-relaxed text-ink-600">{branding.tagline}</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to={branding.allow_signup ? '/register' : '/login'}>
                <Button size="lg">
                  Start free practice <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
              <a href="#courses">
                <Button size="lg" variant="secondary">See the syllabus</Button>
              </a>
            </div>
            <dl className="mt-10 grid max-w-md grid-cols-3 gap-6 border-t border-ink-100 pt-6">
              <div>
                <dt className="text-xs text-ink-500">Questions</dt>
                <dd className="num text-2xl font-bold text-ink-900">{data ? data.questions.toLocaleString() : '—'}</dd>
              </div>
              <div>
                <dt className="text-xs text-ink-500">Courses</dt>
                <dd className="num text-2xl font-bold text-ink-900">{data ? courses.length : '—'}</dd>
              </div>
              <div>
                <dt className="text-xs text-ink-500">Mock tests</dt>
                <dd className="text-2xl font-bold text-ink-900">Unlimited</dd>
              </div>
            </dl>
          </div>

          {/* product preview */}
          <div className="relative hidden lg:block">
            <div className="absolute -right-6 top-10 h-72 w-72 rounded-full bg-accent-200/40 blur-3xl" />
            <div className="relative rounded-3xl border border-ink-200 bg-white p-5 shadow-lift">
              <div className="flex items-center justify-between border-b border-ink-100 pb-4">
                <div>
                  <p className="text-xs font-semibold text-ink-500">Mock test · {featured?.exam_question_count || 50} questions</p>
                  <p className="font-semibold text-ink-900">{featured?.name || 'Officer exam'}</p>
                </div>
                <span className="num rounded-lg bg-ink-900 px-2.5 py-1 font-mono text-sm font-semibold text-white">38:12</span>
              </div>
              <p className="mt-5 text-sm font-medium leading-relaxed text-ink-800">
                Which layer of the OSI model is responsible for end-to-end delivery and segmentation of data?
              </p>
              <div className="mt-4 space-y-2">
                {['Network layer', 'Transport layer', 'Session layer', 'Data link layer'].map((o, i) => (
                  <div
                    key={o}
                    className={`flex items-center gap-3 rounded-xl border px-3 py-2.5 text-sm ${
                      i === 1 ? 'border-brand-500 bg-brand-50 font-semibold text-brand-800' : 'border-ink-200 text-ink-700'
                    }`}
                  >
                    <span className={`grid h-6 w-6 place-items-center rounded-md text-xs font-bold ${i === 1 ? 'bg-brand-600 text-white' : 'bg-ink-100 text-ink-600'}`}>
                      {'ABCD'[i]}
                    </span>
                    {o}
                  </div>
                ))}
              </div>
              <div className="mt-5 grid grid-cols-10 gap-1.5">
                {Array.from({ length: 30 }).map((_, i) => (
                  <span
                    key={i}
                    className={`h-6 rounded-md ${i < 17 ? 'bg-emerald-500' : i === 17 ? 'bg-brand-600' : i === 21 || i === 24 ? 'bg-amber-400' : 'bg-ink-100'}`}
                  />
                ))}
              </div>
            </div>
            <div className="absolute -bottom-6 -left-6 rounded-2xl border border-ink-200 bg-white px-4 py-3 shadow-lift">
              <p className="text-xs text-ink-500">Chapter strength</p>
              <div className="mt-2 space-y-1.5">
                {[['Networks', 82], ['DBMS', 64], ['Security', 41]].map(([n, v]) => (
                  <div key={n} className="flex items-center gap-2 text-xs">
                    <span className="w-16 text-ink-600">{n}</span>
                    <span className="h-1.5 w-24 overflow-hidden rounded-full bg-ink-100">
                      <span className={`block h-full rounded-full ${v > 75 ? 'bg-emerald-500' : v > 50 ? 'bg-amber-400' : 'bg-rose-500'}`} style={{ width: `${v}%` }} />
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* features */}
      <section className="border-y border-ink-100 bg-ink-50/60 py-20">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <p className="eyebrow">Why candidates choose us</p>
          <h2 className="mt-2 max-w-2xl text-3xl font-bold tracking-tight text-ink-900">Everything you need between today and exam day</h2>
          <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {FEATURES.map((f) => (
              <div key={f.title} className="rounded-2xl border border-ink-200 bg-white p-6 shadow-card">
                <div className="grid h-10 w-10 place-items-center rounded-xl bg-brand-50 text-brand-600">
                  <f.icon className="h-5 w-5" />
                </div>
                <h3 className="mt-4 font-semibold text-ink-900">{f.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-ink-600">{f.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* courses */}
      <section id="courses" className="py-20">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <p className="eyebrow">Courses</p>
          <h2 className="mt-2 text-3xl font-bold tracking-tight text-ink-900">Exams we prepare you for</h2>
          <div className="mt-10 grid gap-5 md:grid-cols-2">
            {courses.length === 0 && <p className="text-ink-500">Courses will appear here once published.</p>}
            {courses.map((c) => (
              <div key={c.id} className="flex flex-col rounded-2xl border border-ink-200 bg-white p-6 shadow-card">
                <p className="text-xs font-semibold text-brand-600">{c.exam_name || 'Exam preparation'}</p>
                <h3 className="mt-1 text-xl font-bold text-ink-900">{c.name}</h3>
                <p className="mt-2 flex-1 text-sm leading-relaxed text-ink-600">{c.description}</p>
                <div className="mt-5 grid grid-cols-3 gap-3 rounded-xl bg-ink-50 p-3 text-center">
                  <div>
                    <p className="num text-lg font-bold text-ink-900">{c.exam_question_count}</p>
                    <p className="text-xs text-ink-500">questions</p>
                  </div>
                  <div>
                    <p className="num text-lg font-bold text-ink-900">{c.exam_duration_minutes} min</p>
                    <p className="text-xs text-ink-500">duration</p>
                  </div>
                  <div>
                    <p className="num text-lg font-bold text-ink-900">{Math.round(c.negative_marking * 100)}%</p>
                    <p className="text-xs text-ink-500">negative</p>
                  </div>
                </div>
                <Link to={branding.allow_signup ? '/register' : '/login'} className="mt-5">
                  <Button variant="soft" className="w-full">
                    Start preparing <ArrowRight className="h-4 w-4" />
                  </Button>
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* how it works */}
      <section id="how" className="bg-ink-900 py-20 text-white">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-brand-300">How it works</p>
          <h2 className="mt-2 text-3xl font-bold tracking-tight">From syllabus to selection in four steps</h2>
          <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((s, i) => (
              <div key={s.title} className="rounded-2xl border border-white/10 bg-white/5 p-6">
                <div className="flex items-center gap-3">
                  <span className="num grid h-8 w-8 place-items-center rounded-lg bg-brand-500 text-sm font-bold">{i + 1}</span>
                  <s.icon className="h-5 w-5 text-brand-300" />
                </div>
                <h3 className="mt-4 font-semibold">{s.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-ink-300">{s.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* trust + CTA */}
      <section className="py-20">
        <div className="mx-auto max-w-4xl px-4 text-center sm:px-6">
          <div className="mx-auto mb-6 flex flex-wrap justify-center gap-x-6 gap-y-2 text-sm text-ink-600">
            {['Explanations for every answer', 'Negative marking practice', 'Works on mobile', 'Private & secure'].map((t) => (
              <span key={t} className="inline-flex items-center gap-1.5">
                <CheckCircle2 className="h-4 w-4 text-emerald-500" /> {t}
              </span>
            ))}
          </div>
          <h2 className="text-3xl font-bold tracking-tight text-ink-900 sm:text-4xl">Your exam date is fixed. Your score isn&apos;t.</h2>
          <p className="mx-auto mt-4 max-w-xl text-ink-600">Join {branding.institution_name} and start your first mock test today.</p>
          <Link to={branding.allow_signup ? '/register' : '/login'} className="mt-8 inline-block">
            <Button size="lg">
              Create your free account <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
        </div>
      </section>

      <footer className="border-t border-ink-100 py-8">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-4 text-sm text-ink-500 sm:flex-row sm:px-6">
          <span>© {new Date().getFullYear()} {branding.institution_name}</span>
          <span className="inline-flex items-center gap-1.5">
            <ShieldCheck className="h-4 w-4" /> {branding.support_email ? `Support: ${branding.support_email}` : 'Secure exam preparation platform'}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <FileSearch className="h-4 w-4" /> Questions built from verified study material
          </span>
        </div>
      </footer>
    </div>
  )
}
