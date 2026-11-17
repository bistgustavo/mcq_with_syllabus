import { Link } from 'react-router-dom'
import { ArrowRight, BookOpenText, Clock3, Layers3, ListChecks, MinusCircle } from 'lucide-react'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useAsync } from '../hooks/useAsync'
import { Badge, Button, Card, EmptyState, ErrorBox, PageHeader, Skeleton } from '../components/ui'

export default function Courses() {
  const { isAdmin } = useAuth()
  const { data, error, loading, reload } = useAsync(() => api.courses(), [])

  return (
    <>
      <PageHeader eyebrow="Learn" title="Courses & syllabus" subtitle="Choose your exam to see the full syllabus, practise topics and take mock tests." />
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data ? (
        <div className="grid gap-5 md:grid-cols-2"><Skeleton className="h-64" /><Skeleton className="h-64" /></div>
      ) : (data || []).length === 0 ? (
        <EmptyState icon={BookOpenText} title="No courses yet"
          action={isAdmin && <Link to="/admin/courses"><Button>Create a course</Button></Link>}>
          {isAdmin ? 'Create your first course and paste its syllabus.' : 'Your institution has not published a course yet.'}
        </EmptyState>
      ) : (
        <div className="grid gap-5 md:grid-cols-2">
          {data.map((c) => (
            <Card key={c.id} className="group flex flex-col p-6 transition hover:-translate-y-0.5 hover:shadow-lift">
              <div className="flex items-start justify-between gap-3">
                <div className="grid h-11 w-11 place-items-center rounded-xl bg-brand-600 text-white shadow-sm">
                  <BookOpenText className="h-5 w-5" />
                </div>
                {!c.is_published && <Badge tone="amber">Draft</Badge>}
              </div>
              <p className="mt-4 text-xs font-semibold text-brand-600">{c.exam_name || 'Exam preparation'}</p>
              <h2 className="mt-1 text-xl font-bold tracking-tight text-ink-900">{c.name}</h2>
              <p className="mt-2 line-clamp-2 flex-1 text-sm leading-relaxed text-ink-600">{c.description}</p>
              <div className="mt-5 grid grid-cols-2 gap-x-4 gap-y-2 text-sm text-ink-600 sm:grid-cols-4">
                <span className="flex items-center gap-1.5"><Layers3 className="h-4 w-4 text-ink-400" />{c.chapter_count} chapters</span>
                <span className="flex items-center gap-1.5"><ListChecks className="h-4 w-4 text-ink-400" />{c.question_count} Qs</span>
                <span className="flex items-center gap-1.5"><Clock3 className="h-4 w-4 text-ink-400" />{c.exam_duration_minutes} min</span>
                <span className="flex items-center gap-1.5"><MinusCircle className="h-4 w-4 text-ink-400" />−{Math.round(c.negative_marking * 100)}%</span>
              </div>
              <Link to={`/courses/${c.id}`} className="mt-6">
                <Button variant="soft" className="w-full">
                  Open course <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
            </Card>
          ))}
        </div>
      )}
    </>
  )
}
