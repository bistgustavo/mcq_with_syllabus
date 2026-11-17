import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Award, BarChart3, Bookmark, CheckCircle2, Clock3, MinusCircle, RotateCcw, XCircle } from 'lucide-react'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { Badge, Button, Card, CardHeader, ErrorBox, PageHeader, ProgressBar, Ring, Skeleton, Tabs, cx } from '../components/ui'
import { LETTERS, formatDate, formatDuration, scoreTone, sourceLabel } from '../utils/format'

export default function ExamResult() {
  const { examId } = useParams()
  const { data: r, error, loading, reload } = useAsync(() => api.exam(examId), [examId])
  const [filter, setFilter] = useState('wrong')

  const items = useMemo(() => {
    if (!r?.questions) return []
    return r.questions.map((q, i) => {
      const chosen = r.answers[i]
      const status = chosen === null || chosen === undefined ? 'skipped' : chosen === q.correct_index ? 'correct' : 'wrong'
      return { ...q, n: i + 1, chosen, status, flagged: r.flagged.includes(i) }
    })
  }, [r])

  if (loading && !r) return <div className="space-y-4"><Skeleton className="h-56" /><Skeleton className="h-80" /></div>
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!r) return null
  if (r.status !== 'submitted') {
    return <Card className="p-8 text-center"><p className="text-ink-600">This exam is still in progress.</p><Link to={`/exam/${r.id}`}><Button className="mt-4">Resume exam</Button></Link></Card>
  }

  const lost = Math.round(r.wrong * r.negative_marking * 100) / 100
  const shown = items.filter((q) => filter === 'all' || (filter === 'flagged' ? q.flagged : q.status === filter))

  return (
    <>
      <PageHeader breadcrumb={<Link to="/mock-tests" className="hover:text-ink-800">Mock tests</Link>} eyebrow={r.course_name}
        title={r.paper ? `${r.paper.split(/[:—–]/)[0].trim()} result` : 'Mock test result'}
        subtitle={`${r.paper ? `${r.paper} · ` : ''}Submitted ${formatDate(r.submitted_at)}`}
        actions={<Link to={`/courses/${r.course_id}`}><Button><RotateCcw className="h-4 w-4" /> Take another test</Button></Link>} />

      <Card className="mb-6 overflow-hidden">
        <div className="grid items-center gap-8 p-6 sm:p-8 md:grid-cols-[auto_1fr]">
          <div className="flex flex-col items-center">
            <Ring value={r.percent} size={148} stroke={12} sub={`${r.score} / ${r.max_score ?? r.total} marks`} />
            <Badge tone={r.passed ? 'green' : 'red'} className="mt-4 px-3 py-1 text-sm">
              {r.passed ? <><Award className="h-4 w-4" /> Passed</> : <>Below pass mark ({r.pass_percent}%)</>}
            </Badge>
          </div>
          <div>
            <h2 className="text-xl font-bold text-ink-900">
              {r.passed ? 'Well done, you cleared the pass mark.' : 'Keep going, you are building the foundation.'}
            </h2>
            <p className="mt-1 text-sm text-ink-500">
              {(r.marking?.lines || [`Score = correct answers − ${r.negative_marking} × wrong answers.`]).slice(0, 2).join(' ')}
            </p>
            <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                [CheckCircle2, 'Correct', r.correct, 'text-emerald-600'],
                [XCircle, 'Wrong', r.wrong, 'text-rose-600'],
                [MinusCircle, 'Skipped', r.skipped, 'text-ink-500'],
                [Clock3, 'Time taken', formatDuration(r.duration_seconds), 'text-ink-900'],
              ].map(([Icon, k, v, c]) => (
                <div key={k} className="rounded-xl bg-ink-50 p-3">
                  <p className="flex items-center gap-1.5 text-xs text-ink-500"><Icon className="h-3.5 w-3.5" /> {k}</p>
                  <p className={cx('num mt-1 text-xl font-bold', c)}>{v}</p>
                </div>
              ))}
            </div>
            {lost > 0 && <p className="mt-4 text-sm text-rose-600">Negative marking cost you <strong>{lost}</strong> mark{lost === 1 ? '' : 's'}. When you're unsure, skipping can be the better move.</p>}
          </div>
        </div>
      </Card>

      {r.section_results?.length > 1 && (
        <div className="mb-6">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-lg font-bold text-ink-900">Result by paper</h2>
            <p className="text-xs text-ink-500">
              {r.pass_rule === 'per_paper' ? `You must score at least ${r.pass_percent}% in every paper.` : `The combined score must reach ${r.pass_percent}%.`}
            </p>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            {r.section_results.map((s) => (
              <Card key={s.paper} className={cx('p-5', s.passed ? '' : 'border-rose-200')}>
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-semibold text-ink-900">{s.paper}</p>
                  <Badge tone={s.passed ? 'green' : 'red'}>{s.passed ? 'Pass' : 'Fail'}</Badge>
                </div>
                <p className={cx('num mt-3 text-3xl font-bold', scoreTone(s.percent))}>{s.percent}%</p>
                <p className="num text-sm text-ink-500">{s.score} / {s.max_score} marks</p>
                <p className="num mt-2 text-xs text-ink-500">{s.correct} correct · {s.wrong} wrong · {s.skipped} skipped</p>
              </Card>
            ))}
          </div>
        </div>
      )}

      <Card className="mb-6">
        <CardHeader icon={BarChart3} title="Chapter-wise analysis" subtitle="Weakest chapters first. Revise these before your next test." />
        <div className="divide-y divide-ink-100">
          {r.chapter_breakdown.map((b) => (
            <div key={b.chapter_id} className="grid items-center gap-3 px-5 py-3.5 sm:grid-cols-[1fr_180px_120px]">
              <p className="font-medium text-ink-800">{b.chapter_name}</p>
              <ProgressBar value={b.percent} />
              <p className="num text-right text-sm">
                <span className={cx('font-bold', scoreTone(b.percent))}>{b.percent}%</span>{' '}
                <span className="text-ink-500">({b.correct}✓ {b.wrong}✗ {b.skipped}–)</span>
              </p>
            </div>
          ))}
        </div>
      </Card>

      <h2 className="mb-3 text-lg font-bold text-ink-900">Answer review</h2>
      <Tabs value={filter} onChange={setFilter} tabs={[
        { value: 'wrong', label: 'Wrong', icon: XCircle, count: r.wrong },
        { value: 'skipped', label: 'Skipped', icon: MinusCircle, count: r.skipped },
        { value: 'flagged', label: 'Marked', icon: Bookmark, count: items.filter((q) => q.flagged).length },
        { value: 'correct', label: 'Correct', icon: CheckCircle2, count: r.correct },
        { value: 'all', label: 'All', count: items.length },
      ]} />

      <div className="space-y-4">
        {shown.length === 0 && <p className="py-10 text-center text-sm text-ink-500">Nothing here.</p>}
        {shown.map((q) => (
          <Card key={q.id} className="p-5 sm:p-6">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <span className="num rounded-md bg-ink-100 px-2 py-0.5 text-xs font-bold text-ink-700">Q{q.n}</span>
              <span className="text-xs text-ink-500">{q.chapter_name} · {q.topic_name}</span>
              {(q.source === 'past_paper' || q.source === 'online') && (
                <Badge tone={sourceLabel(q.source, q.reference).tone}>{sourceLabel(q.source, q.reference).text}</Badge>
              )}
              <span className="ml-auto">
                {q.status === 'correct' ? <Badge tone="green">+1</Badge> : q.status === 'wrong' ? <Badge tone="red">−{r.negative_marking}</Badge> : <Badge>0</Badge>}
              </span>
            </div>
            <p className="font-semibold leading-relaxed text-ink-900">{q.question_text}</p>
            <ul className="mt-4 space-y-2">
              {q.options.map((opt, i) => {
                const right = i === q.correct_index
                const mine = i === q.chosen
                return (
                  <li key={i} className={cx('flex items-start gap-3 rounded-xl border px-3.5 py-2.5 text-sm',
                    right ? 'border-emerald-300 bg-emerald-50 text-emerald-900' : mine ? 'border-rose-300 bg-rose-50 text-rose-900' : 'border-ink-200 text-ink-700')}>
                    <span className="font-bold">{LETTERS[i]}.</span>
                    <span className="flex-1">{opt}</span>
                    {right && <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />}
                    {mine && !right && <span className="text-xs font-semibold">Your answer</span>}
                  </li>
                )
              })}
            </ul>
            {q.explanation && (
              <p className="mt-4 rounded-xl bg-brand-50/60 px-4 py-3 text-sm leading-relaxed text-ink-700">
                <span className="font-semibold text-brand-800">Explanation: </span>{q.explanation}
              </p>
            )}
          </Card>
        ))}
      </div>
    </>
  )
}
