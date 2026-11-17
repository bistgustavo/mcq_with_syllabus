import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { CheckCircle2, Clock3, RotateCcw, XCircle } from 'lucide-react'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { Badge, Button, Card, DifficultyBadge, ErrorBox, Ring, Skeleton, Toggle, cx } from '../components/ui'
import { LETTERS, formatDate, formatDuration, sourceLabel } from '../utils/format'

export default function ResultPage() {
  const { attemptId } = useParams()
  const { data, error, loading, reload } = useAsync(() => api.attempt(attemptId), [attemptId])
  const [onlyWrong, setOnlyWrong] = useState(false)

  if (loading && !data) return <div className="space-y-4"><Skeleton className="h-56" /><Skeleton className="h-64" /></div>
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!data) return null

  const items = onlyWrong ? data.results.filter((r) => !r.is_correct) : data.results
  const message = data.percent >= 80 ? 'Excellent work!' : data.percent >= 50 ? 'Good effort. Review the misses below.' : 'Keep going. The explanations below will help.'

  return (
    <div className="mx-auto max-w-3xl">
      <Card className="mb-8 p-8">
        <div className="flex flex-col items-center gap-6 sm:flex-row sm:items-center">
          <Ring value={data.percent} size={128} sub={`${data.score}/${data.total}`} />
          <div className="flex-1 text-center sm:text-left">
            <p className="text-sm text-ink-500">Practice quiz · {formatDate(data.created_at)}</p>
            <h1 className="mt-1 text-2xl font-bold tracking-tight text-ink-900">{message}</h1>
            <div className="mt-3 flex flex-wrap items-center justify-center gap-3 text-sm text-ink-500 sm:justify-start">
              {data.difficulty && <DifficultyBadge value={data.difficulty} />}
              <span className="flex items-center gap-1"><Clock3 className="h-4 w-4" /> {formatDuration(data.duration_seconds)}</span>
            </div>
            <div className="mt-5 flex flex-wrap justify-center gap-2 sm:justify-start">
              <Link to={`/topics/${data.topic_id}/quiz?count=${data.total}${data.difficulty ? `&difficulty=${data.difficulty}` : ''}`}>
                <Button><RotateCcw className="h-4 w-4" /> Practise again</Button>
              </Link>
              <Link to={`/topics/${data.topic_id}`}><Button variant="secondary">Back to topic</Button></Link>
            </div>
          </div>
        </div>
      </Card>

      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-bold text-ink-900">Review</h2>
        <Toggle checked={onlyWrong} onChange={setOnlyWrong} label="Only mistakes" />
      </div>

      <div className="space-y-4">
        {items.map((r) => (
          <Card key={r.question_id} className="p-5 sm:p-6">
            <div className="mb-3 flex items-start gap-3">
              {r.is_correct ? <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-500" /> : <XCircle className="mt-0.5 h-5 w-5 shrink-0 text-rose-500" />}
              <p className="flex-1 font-semibold leading-relaxed text-ink-900">{data.results.indexOf(r) + 1}. {r.question_text}</p>
              {(r.source === 'past_paper' || r.source === 'online') && (
                <Badge tone={sourceLabel(r.source, r.reference).tone}>{sourceLabel(r.source, r.reference).text}</Badge>
              )}
            </div>
            <ul className="space-y-2 sm:pl-8">
              {r.options.map((opt, i) => {
                const right = i === r.correct_index
                const mine = i === r.selected_index
                return (
                  <li key={i} className={cx('flex gap-3 rounded-xl border px-3.5 py-2.5 text-sm',
                    right ? 'border-emerald-300 bg-emerald-50 text-emerald-900' : mine ? 'border-rose-300 bg-rose-50 text-rose-900' : 'border-ink-200 text-ink-700')}>
                    <span className="font-bold">{LETTERS[i]}.</span><span className="flex-1">{opt}</span>
                    {mine && <span className="text-xs font-semibold">Your answer</span>}
                  </li>
                )
              })}
            </ul>
            {r.selected_index === null && <p className="mt-2 text-xs font-medium text-amber-600 sm:pl-8">Not answered</p>}
            {r.explanation && (
              <p className="mt-4 rounded-xl bg-brand-50/60 px-4 py-3 text-sm leading-relaxed text-ink-700 sm:ml-8">
                <span className="font-semibold text-brand-800">Explanation: </span>{r.explanation}
              </p>
            )}
          </Card>
        ))}
        {items.length === 0 && <p className="py-8 text-center text-sm text-ink-500">No mistakes. Nice work!</p>}
      </div>
    </div>
  )
}
