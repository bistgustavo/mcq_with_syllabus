import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { BookOpen, Play, Settings2, Target, Users } from 'lucide-react'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useAsync } from '../hooks/useAsync'
import GenerationPanel from '../components/GenerationPanel'
import { Button, Card, DifficultyBadge, ErrorBox, Notice, PageHeader, Skeleton, Stat, cx } from '../components/ui'
import { DIFFICULTIES } from '../utils/format'

export default function TopicPage() {
  const { topicId } = useParams()
  const { isAdmin } = useAuth()
  const navigate = useNavigate()
  const { data, error, loading, reload } = useAsync(
    () => Promise.all([api.topic(topicId), api.topicStats(topicId)]).then(([topic, stats]) => ({ topic, stats })),
    [topicId],
  )
  const [count, setCount] = useState(10)
  const [difficulty, setDifficulty] = useState('')

  if (loading && !data) return <div className="space-y-4"><Skeleton className="h-24" /><Skeleton className="h-64" /></div>
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!data) return null
  const { topic, stats } = data
  const byDiff = topic.question_count_by_difficulty || {}
  const available = difficulty ? byDiff[difficulty] || 0 : topic.question_count

  const start = () => {
    const params = new URLSearchParams({ count: String(count) })
    if (difficulty) params.set('difficulty', difficulty)
    navigate(`/topics/${topic.id}/quiz?${params}`)
  }

  return (
    <>
      <PageHeader
        breadcrumb={
          <>
            <Link to="/courses" className="hover:text-ink-800">Courses</Link> /{' '}
            <Link to={`/courses/${topic.course_id}`} className="hover:text-ink-800">{topic.course_name}</Link> / {topic.chapter_name}
          </>
        }
        title={topic.name}
        actions={isAdmin && <Link to={`/admin/topics/${topic.id}`}><Button variant="secondary"><Settings2 className="h-4 w-4" /> Manage topic</Button></Link>}
      />

      {topic.description && (
        <Card className="mb-6 flex gap-3 p-5">
          <BookOpen className="mt-0.5 h-5 w-5 shrink-0 text-brand-600" />
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-ink-500">Syllabus coverage</p>
            <p className="mt-1 text-sm leading-relaxed text-ink-700">{topic.description}</p>
          </div>
        </Card>
      )}

      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <Stat icon={Target} label="Questions available" value={topic.question_count} />
        <Stat icon={Users} label="Quizzes taken here" value={stats.attempts} tone="violet" />
        <Stat icon={Play} label="Average score" value={stats.attempts ? `${stats.avg_percent}%` : '—'} tone="green" />
      </div>

      <div className={cx('grid gap-6', isAdmin && 'lg:grid-cols-3')}>
        <Card className={cx('p-6', isAdmin && 'lg:col-span-2')}>
          <h2 className="text-lg font-bold text-ink-900">Practice quiz</h2>
          <p className="mt-1 text-sm text-ink-500">Questions you haven&apos;t seen come first. Each answer comes with an explanation.</p>

          <p className="mb-2 mt-6 text-sm font-medium text-ink-700">Difficulty</p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {[['', 'Mixed', topic.question_count], ...DIFFICULTIES.map((d) => [d, d[0].toUpperCase() + d.slice(1), byDiff[d] || 0])].map(([value, label, n]) => (
              <button key={label} onClick={() => setDifficulty(value)}
                className={cx('rounded-xl border px-3 py-3 text-left transition',
                  difficulty === value ? 'border-brand-500 bg-brand-50 ring-1 ring-brand-500' : 'border-ink-200 hover:border-ink-300')}>
                <span className="block text-sm font-semibold text-ink-900">{label}</span>
                <span className="text-xs text-ink-500">{n} questions</span>
              </button>
            ))}
          </div>

          <p className="mb-2 mt-6 text-sm font-medium text-ink-700">Number of questions</p>
          <div className="flex flex-wrap gap-2">
            {[5, 10, 15, 20, 30].map((n) => (
              <button key={n} onClick={() => setCount(n)}
                className={cx('num h-10 w-14 rounded-xl border text-sm font-semibold transition',
                  count === n ? 'border-brand-500 bg-brand-600 text-white' : 'border-ink-200 text-ink-700 hover:border-ink-300')}>
                {n}
              </button>
            ))}
          </div>

          <div className="mt-8 flex flex-wrap items-center gap-4">
            <Button size="lg" onClick={start} disabled={available === 0}><Play className="h-4 w-4" /> Start practice</Button>
            {available > 0 && available < count && <span className="text-sm text-ink-500">{available} available, so the quiz will be shorter.</span>}
          </div>
          {available === 0 && (
            <Notice tone="warn" className="mt-4">
              {isAdmin ? 'No questions yet. Generate some with the panel on the right.' : 'Questions for this topic are being prepared. Check back soon.'}
            </Notice>
          )}
          <div className="mt-6 flex flex-wrap gap-2">
            {DIFFICULTIES.map((d) => <span key={d} className="inline-flex items-center gap-1.5 text-xs text-ink-500"><DifficultyBadge value={d} /> {byDiff[d] || 0}</span>)}
          </div>
        </Card>

        {isAdmin && (
          <GenerationPanel topicId={topic.id} hasContent={topic.has_content} defaultDifficulty={difficulty || 'medium'}
            onGenerated={() => reload({ silent: true })} />
        )}
      </div>
    </>
  )
}
