import { Link } from 'react-router-dom'
import { Activity, ArrowRight, BookOpenText, Cloud, Cpu, FileText, Library, ListChecks, Palette, RefreshCw, Server, Users } from 'lucide-react'
import { api } from '../../api/client'
import { useAsync } from '../../hooks/useAsync'
import { Badge, Button, Card, CardHeader, ErrorBox, PageHeader, Skeleton, Stat, cx } from '../../components/ui'

const LABELS = {
  database: ['MySQL database', Server],
  redis: ['Redis (task queue)', Server],
  qdrant: ['Qdrant (knowledge base)', Server],
  worker: ['Background worker', Cpu],
  groq: ['Groq (cloud AI)', Cloud],
  gemini: ['Gemini (cloud AI)', Cloud],
  ollama: ['Ollama (local AI)', Cpu],
}

function Health() {
  const { data, error, loading, reload } = useAsync(() => api.health(), [])
  const infra = data?.infrastructure || {}
  const mode = (k) => infra[k]?.mode
  return (
    <Card>
      <CardHeader icon={Activity} title="System health"
        subtitle={data ? `AI order: ${data.llm_order.join(' → ')}` : 'Checking services…'}
        actions={<>
          {data && <Badge tone={data.status === 'ok' ? 'green' : 'amber'}>{data.status === 'ok' ? 'All systems go' : 'Degraded'}</Badge>}
          <Button variant="ghost" size="sm" onClick={() => reload()} loading={loading} aria-label="Re-check"><RefreshCw className="h-4 w-4" /></Button>
        </>} />
      <ErrorBox error={error} />
      {!data ? <div className="p-5"><Skeleton className="h-48" /></div> : (
        <ul className="divide-y divide-ink-100">
          {Object.entries(LABELS).map(([key, [label, Icon]]) => {
            const c = data.checks[key] || {}
            const optional = key === 'groq' || key === 'gemini'
            const m = key === 'redis' || key === 'qdrant' ? mode(key) : null
            return (
              <li key={key} className="flex items-start gap-3 px-5 py-3">
                <span className={cx('mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full', c.ok ? 'bg-emerald-500' : optional ? 'bg-ink-300' : 'bg-rose-500')} />
                <Icon className="mt-0.5 h-4 w-4 shrink-0 text-ink-400" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-ink-800">{label}</p>
                  {m && <p className="text-xs text-ink-500">{m === 'cloud' ? 'Using cloud' : 'Using local fallback'}{infra[key]?.note ? ' (cloud unreachable)' : ''}</p>}
                  {key === 'ollama' && c.ok && !c.model_available && <p className="text-xs text-amber-600">Model {c.model} not downloaded</p>}
                  {optional && !c.configured && <p className="text-xs text-ink-400">No API key configured</p>}
                  {c.error && !optional && <p className="break-words text-xs text-rose-600">{c.error}</p>}
                </div>
                {c.ms !== undefined && <span className="num text-xs text-ink-400">{c.ms} ms</span>}
              </li>
            )
          })}
        </ul>
      )}
    </Card>
  )
}

export default function AdminHome() {
  const { data: o, error, reload } = useAsync(() => api.overview(), [])
  return (
    <>
      <PageHeader eyebrow="Administration" title="Overview" subtitle="Your institution's content, students and system status at a glance." />
      <ErrorBox error={error} onRetry={reload} />
      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat icon={BookOpenText} label="Courses" value={o?.courses ?? '—'} hint={o && `${o.chapters} chapters · ${o.topics} topics`} />
        <Stat icon={FileText} label="Topics with content" value={o ? `${o.topics_with_content}/${o.topics}` : '—'} hint={o && `${o.documents} PDF(s) uploaded`} tone="green" />
        <Stat icon={ListChecks} label="Question bank" value={o?.questions?.toLocaleString() ?? '—'}
          hint={o && (Object.entries(o.questions_by_source).map(([k, v]) => `${k} ${v}`).join(' · ') || 'empty')} tone="violet" />
        <Stat icon={Users} label="Students" value={o?.users ?? '—'} hint={o && `${o.attempts} practice quizzes`} tone="amber" />
      </div>
      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2 h-fit">
          {[
            ['/admin/courses', Library, 'Courses & content', 'Create courses, paste the syllabus, upload PDFs and build the question bank.'],
            ['/admin/users', Users, 'Students & staff', 'Manage accounts, give admin access or disable users.'],
            ['/admin/settings', Palette, 'Branding & settings', 'Your institution name, colours, logo and sign-up policy.'],
            ['/courses', BookOpenText, 'Student view', 'See the platform exactly as your students do.'],
          ].map(([to, Icon, title, body]) => (
            <Link key={to} to={to}>
              <Card className="group h-full p-5 transition hover:-translate-y-0.5 hover:shadow-lift">
                <div className="flex items-center justify-between">
                  <span className="grid h-10 w-10 place-items-center rounded-xl bg-brand-50 text-brand-600"><Icon className="h-5 w-5" /></span>
                  <ArrowRight className="h-4 w-4 text-ink-300 transition group-hover:translate-x-0.5 group-hover:text-brand-600" />
                </div>
                <p className="mt-4 font-semibold text-ink-900">{title}</p>
                <p className="mt-1 text-sm text-ink-500">{body}</p>
              </Card>
            </Link>
          ))}
        </div>
        <Health />
      </div>
    </>
  )
}
