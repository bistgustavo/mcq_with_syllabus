import { Link } from 'react-router-dom'
import {
  ArrowRight,
  BookOpenText,
  CheckCircle2,
  ClipboardCheck,
  Flame,
  Target,
  TrendingDown,
  Trophy,
} from 'lucide-react'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useAsync } from '../hooks/useAsync'
import { Badge, Button, Card, CardHeader, ErrorBox, PageHeader, ProgressBar, Skeleton, Stat, cx } from '../components/ui'
import { scoreTone, timeAgo } from '../utils/format'

function greeting() {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
}

function ScoreTrend({ exams, passPercent = 40 }) {
  const items = exams.filter((e) => e.status === 'submitted').slice(0, 10).reverse()
  if (!items.length) {
    return <p className="py-10 text-center text-sm text-ink-500">Your mock test scores will appear here.</p>
  }
  return (
    <div className="relative h-48">
      <div className="absolute inset-x-0 border-t border-dashed border-rose-300" style={{ bottom: `${passPercent}%` }}>
        <span className="absolute -top-5 right-0 text-[11px] font-medium text-rose-500">pass {passPercent}%</span>
      </div>
      <div className="flex h-full items-end gap-2">
        {items.map((e) => (
          <Link key={e.id} to={`/exam/${e.id}/result`} className="group flex h-full flex-1 flex-col justify-end" title={`${e.percent}%`}>
            <span className="num mb-1 text-center text-[11px] font-semibold text-ink-500 opacity-0 transition group-hover:opacity-100">
              {e.percent}%
            </span>
            <span
              className={cx('w-full rounded-t-lg transition-all group-hover:opacity-80', e.passed ? 'bg-brand-500' : 'bg-ink-300')}
              style={{ height: `${Math.max(4, e.percent)}%` }}
            />
          </Link>
        ))}
      </div>
    </div>
  )
}

export default function Dashboard() {
  const { user } = useAuth()
  const { data, error, loading, reload } = useAsync(
    () => Promise.all([api.dashboard(), api.myExams(), api.courses()]).then(([practice, exams, courses]) => ({ practice, exams, courses })),
    [],
  )
  const firstName = (user?.full_name || '').split(' ')[0]

  if (loading && !data) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-72" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-28" />)}
        </div>
        <Skeleton className="h-64" />
      </div>
    )
  }
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!data) return null

  const { practice, exams, courses } = data
  const course = courses.find((c) => c.is_published) || courses[0]
  const submitted = exams.filter((e) => e.status === 'submitted')
  const running = exams.find((e) => e.status === 'in_progress')
  const best = submitted.length ? Math.max(...submitted.map((e) => e.percent)) : null
  const accuracy = practice.questions_answered ? Math.round((100 * practice.correct_answers) / practice.questions_answered) : null
  const isNew = !submitted.length && !practice.attempts

  return (
    <>
      <PageHeader
        eyebrow={greeting()}
        title={firstName ? `${firstName}, let's get you exam-ready.` : "Let's get you exam-ready."}
        subtitle={
          courses.length > 1
            ? `${courses.length} courses: ${courses.map((c) => c.name).join(' · ')}`
            : course ? `Preparing for ${course.exam_name || course.name}` : undefined
        }
        actions={
          course &&
          (running ? (
            <Link to={`/exam/${running.id}`}>
              <Button variant="accent">
                Resume mock test <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
          ) : (
            <Link to="/mock-tests">
              <Button>
                <ClipboardCheck className="h-4 w-4" /> Take a mock test
              </Button>
            </Link>
          ))
        }
      />

      {isNew ? (
        <Card className="overflow-hidden">
          <div className="grid gap-8 p-8 md:grid-cols-[1.2fr_1fr]">
            <div>
              <Badge tone="blue">Getting started</Badge>
              <h2 className="mt-3 text-2xl font-bold tracking-tight text-ink-900">Three steps to your first score</h2>
              <ol className="mt-6 space-y-4">
                {[
                  ['Explore the syllabus', 'See every chapter and its weight in the exam.', '/courses', BookOpenText],
                  ['Practise a topic', 'Short quizzes with explanations to warm up.', course ? `/courses/${course.id}` : '/courses', Target],
                  ['Sit a full mock test', 'Timed, negative marking, just like the real paper.', '/mock-tests', ClipboardCheck],
                ].map(([title, body, to, Icon], i) => (
                  <li key={title}>
                    <Link to={to} className="group flex items-start gap-4 rounded-xl p-2 -m-2 hover:bg-ink-50">
                      <span className="num grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-brand-600 text-sm font-bold text-white">{i + 1}</span>
                      <span className="flex-1">
                        <span className="flex items-center gap-2 font-semibold text-ink-900">
                          <Icon className="h-4 w-4 text-brand-600" /> {title}
                        </span>
                        <span className="text-sm text-ink-500">{body}</span>
                      </span>
                      <ArrowRight className="mt-2 h-4 w-4 text-ink-300 transition group-hover:translate-x-0.5 group-hover:text-brand-600" />
                    </Link>
                  </li>
                ))}
              </ol>
            </div>
            {course && (
              <div className="rounded-2xl bg-gradient-to-br from-brand-600 to-brand-800 p-6 text-white">
                <p className="text-sm text-brand-100">Exam pattern</p>
                <p className="mt-1 text-xl font-bold">{course.exam_name || course.name}</p>
                <dl className="mt-6 grid grid-cols-2 gap-4">
                  {[
                    ['Questions', course.exam_question_count],
                    ['Duration', `${course.exam_duration_minutes} min`],
                    ['Negative marking', `${Math.round(course.negative_marking * 100)}%`],
                    ['Pass mark', `${course.pass_percent}%`],
                  ].map(([k, v]) => (
                    <div key={k} className="rounded-xl bg-white/10 p-3">
                      <dt className="text-xs text-brand-100">{k}</dt>
                      <dd className="num text-lg font-bold">{v}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            )}
          </div>
        </Card>
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat icon={ClipboardCheck} label="Mock tests taken" value={submitted.length} hint={running ? 'One in progress' : undefined} />
            <Stat icon={Trophy} label="Best mock score" value={best === null ? '—' : `${best}%`} tone="amber" />
            <Stat icon={Target} label="Practice accuracy" value={accuracy === null ? '—' : `${accuracy}%`} tone="green"
              hint={`${practice.correct_answers}/${practice.questions_answered} correct`} />
            <Stat icon={Flame} label="Topics practised" value={practice.topics_practiced} tone="violet" />
          </div>

          <div className="grid gap-6 lg:grid-cols-5">
            <Card className="lg:col-span-3">
              <CardHeader icon={Trophy} title="Mock test scores" subtitle="Your last 10 full-length tests" />
              <div className="p-5">
                <ScoreTrend exams={exams} passPercent={course?.pass_percent} />
              </div>
            </Card>
            <Card className="lg:col-span-2">
              <CardHeader icon={TrendingDown} title="Needs practice" subtitle="Topics with your lowest scores" />
              <div className="space-y-4 p-5">
                {practice.weakest_topics.length === 0 && <p className="text-sm text-ink-500">Practise a few topics to see this.</p>}
                {practice.weakest_topics.map((t) => (
                  <Link key={t.topic_id} to={`/topics/${t.topic_id}`} className="block group">
                    <div className="mb-1.5 flex items-center justify-between gap-2 text-sm">
                      <span className="truncate font-medium text-ink-800 group-hover:text-brand-700">{t.topic_name}</span>
                      <span className={cx('num font-semibold', scoreTone(t.avg_percent))}>{t.avg_percent}%</span>
                    </div>
                    <ProgressBar value={t.avg_percent} />
                  </Link>
                ))}
              </div>
            </Card>
          </div>

          <Card>
            <CardHeader icon={CheckCircle2} title="Recent activity" actions={<Link to="/history" className="text-sm font-semibold text-brand-600 hover:underline">View all</Link>} />
            <ul className="divide-y divide-ink-100">
              {[
                ...submitted.slice(0, 5).map((e) => ({ key: `e${e.id}`, to: `/exam/${e.id}/result`, title: `Mock test · ${e.course_name}`,
                  meta: `${e.correct} correct · ${e.wrong} wrong · ${e.skipped} skipped`, when: e.submitted_at, pct: e.percent, kind: 'Mock' })),
                ...practice.recent.slice(0, 5).map((a) => ({ key: `p${a.id}`, to: `/attempts/${a.id}`, title: a.topic_name,
                  meta: `${a.score}/${a.total} correct`, when: a.created_at, pct: a.percent, kind: 'Practice' })),
              ]
                .sort((a, b) => String(b.when).localeCompare(String(a.when)))
                .slice(0, 6)
                .map((r) => (
                  <li key={r.key}>
                    <Link to={r.to} className="flex items-center gap-4 px-5 py-3.5 hover:bg-ink-50">
                      <Badge tone={r.kind === 'Mock' ? 'blue' : 'slate'}>{r.kind}</Badge>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-semibold text-ink-900">{r.title}</p>
                        <p className="text-xs text-ink-500">{r.meta} · {timeAgo(r.when)}</p>
                      </div>
                      <span className={cx('num text-sm font-bold', scoreTone(r.pct))}>{r.pct}%</span>
                    </Link>
                  </li>
                ))}
            </ul>
          </Card>
        </div>
      )}
    </>
  )
}
