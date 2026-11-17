import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ClipboardCheck, History, Target } from 'lucide-react'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { Badge, Button, Card, DifficultyBadge, EmptyState, ErrorBox, PageHeader, Skeleton, Tabs, cx } from '../components/ui'
import { formatDate, formatDuration, scoreTone } from '../utils/format'

const PAGE = 25

function PracticeHistory() {
  const [offset, setOffset] = useState(0)
  const { data, error, loading, reload } = useAsync(() => api.attempts({ limit: PAGE + 1, offset }), [offset])
  const rows = (data || []).slice(0, PAGE)
  if (loading && !data) return <Skeleton className="h-64" />
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!rows.length && offset === 0) {
    return <EmptyState icon={Target} title="No practice quizzes yet" action={<Link to="/courses"><Button>Find a topic</Button></Link>} />
  }
  return (
    <Card className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-xs uppercase tracking-wide text-ink-500">
          <tr><th className="px-5 py-3">Topic</th><th className="px-5 py-3">Score</th><th className="px-5 py-3">Level</th><th className="px-5 py-3">Time</th><th className="px-5 py-3">Date</th></tr>
        </thead>
        <tbody className="divide-y divide-ink-100">
          {rows.map((a) => (
            <tr key={a.id} className="hover:bg-ink-50">
              <td className="px-5 py-3">
                <Link to={`/attempts/${a.id}`} className="font-semibold text-ink-900 hover:text-brand-700">{a.topic_name}</Link>
                <p className="text-xs text-ink-500">{a.course_name}</p>
              </td>
              <td className={cx('num px-5 py-3 font-bold', scoreTone(a.percent))}>{a.score}/{a.total} · {a.percent}%</td>
              <td className="px-5 py-3"><DifficultyBadge value={a.difficulty} /></td>
              <td className="num px-5 py-3 text-ink-500">{formatDuration(a.duration_seconds)}</td>
              <td className="px-5 py-3 text-ink-500">{formatDate(a.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="flex justify-between border-t border-ink-100 px-5 py-3">
        <Button variant="secondary" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Newer</Button>
        <Button variant="secondary" size="sm" disabled={(data || []).length <= PAGE} onClick={() => setOffset(offset + PAGE)}>Older</Button>
      </div>
    </Card>
  )
}

function MockHistory() {
  const { data, error, loading, reload } = useAsync(() => api.myExams(), [])
  if (loading && !data) return <Skeleton className="h-64" />
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!data.length) {
    return <EmptyState icon={ClipboardCheck} title="No mock tests yet" action={<Link to="/mock-tests"><Button>Take a mock test</Button></Link>} />
  }
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {data.map((e) => (
        <Link key={e.id} to={e.status === 'submitted' ? `/exam/${e.id}/result` : `/exam/${e.id}`}>
          <Card className="flex items-center gap-5 p-5 transition hover:shadow-lift">
            <div className={cx('num grid h-16 w-16 shrink-0 place-items-center rounded-2xl text-lg font-bold',
              e.status !== 'submitted' ? 'bg-violet-50 text-violet-700' : e.passed ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700')}>
              {e.status === 'submitted' ? `${Math.round(e.percent)}%` : '…'}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate font-semibold text-ink-900">{e.course_name}</p>
              <p className="text-xs text-ink-500">{formatDate(e.submitted_at || e.started_at)}</p>
              {e.status === 'submitted' && <p className="num mt-1 text-xs text-ink-600">{e.correct} correct · {e.wrong} wrong · {e.skipped} skipped · {e.score} marks</p>}
            </div>
            {e.status !== 'submitted' ? <Badge tone="violet">Resume</Badge> : e.passed ? <Badge tone="green">Pass</Badge> : <Badge tone="red">Below pass</Badge>}
          </Card>
        </Link>
      ))}
    </div>
  )
}

export default function HistoryPage() {
  const [tab, setTab] = useState('mock')
  return (
    <>
      <PageHeader eyebrow="Progress" title="My results" subtitle="Every mock test and practice quiz you've taken. Open one to review the answers." />
      <Tabs value={tab} onChange={setTab} tabs={[{ value: 'mock', label: 'Mock tests', icon: ClipboardCheck }, { value: 'practice', label: 'Practice quizzes', icon: History }]} />
      {tab === 'mock' ? <MockHistory /> : <PracticeHistory />}
    </>
  )
}
