import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowRight, ChevronDown, ClipboardCheck, Clock3, Info, ListChecks, MinusCircle, Play, Settings2, Target } from 'lucide-react'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { ExamIntro } from './MockTests'
import { PaperLink } from '../components/PastPapers'
import { useAsync } from '../hooks/useAsync'
import { Badge, Button, Card, ErrorBox, Notice, PageHeader, ProgressBar, Skeleton, cx } from '../components/ui'
import { groupByPaper, paperShort, papersOf, scoreTone } from '../utils/format'

export default function CourseDetail() {
  const { courseId } = useParams()
  const { isAdmin } = useAuth()
  const [open, setOpen] = useState({})
  const [intro, setIntro] = useState(false)
  const { data, error, loading, reload } = useAsync(
    () =>
      Promise.all([api.course(courseId), api.readiness(courseId), api.dashboard(), api.pastPapers(courseId).catch(() => ({ papers: [] }))]).then(([course, readiness, dash, pp]) => ({
        course,
        readiness,
        pastPapers: pp.papers.filter((x) => x.file_url || x.has_file),
        progress: Object.fromEntries(dash.topics.map((t) => [t.topic_id, t])),
      })),
    [courseId],
  )

  if (loading && !data) return <div className="space-y-4"><Skeleton className="h-40" /><Skeleton className="h-96" /></div>
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!data) return null
  const { course, readiness, progress, pastPapers } = data

  const neededByChapter = Object.fromEntries(readiness.chapters.map((c) => [c.chapter_id, c]))
  const papers = papersOf(course.chapters)
  const groups = groupByPaper(course.chapters)
  const allOpen = course.chapters.every((c) => open[c.id])

  return (
    <>
      <PageHeader
        breadcrumb={<Link to="/courses" className="hover:text-ink-800">Courses</Link>}
        eyebrow={course.exam_name}
        title={course.name}
        subtitle={course.description}
        actions={
          isAdmin && (
            <Link to={`/admin/courses/${course.id}`}>
              <Button variant="secondary"><Settings2 className="h-4 w-4" /> Manage</Button>
            </Link>
          )
        }
      />

      <Card className="mb-8 overflow-hidden">
        <div className="grid lg:grid-cols-[1fr_auto]">
          <div className="p-6">
            <p className="flex items-center gap-2 font-semibold text-ink-900"><ClipboardCheck className="h-5 w-5 text-brand-600" /> Full-length mock test</p>
            <p className="mt-1 text-sm text-ink-500">
              {papers.length > 1
                ? `${papers.length} papers. Take one paper at a time or all of them back to back; questions follow each unit's official weightage.`
                : 'Questions are drawn from every chapter according to the exam\'s weightage.'}
            </p>
            <dl className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                [ListChecks, papers.length > 1 ? 'Questions / paper' : 'Questions', course.exam_question_count],
                [Clock3, papers.length > 1 ? 'Time / paper' : 'Duration', `${course.exam_duration_minutes} min`],
                [MinusCircle, 'Negative', `${Math.round(course.negative_marking * 100)}% / wrong`],
                [Target, 'Pass mark', `${course.pass_percent}%`],
              ].map(([Icon, k, v]) => (
                <div key={k} className="rounded-xl bg-ink-50 px-3 py-2.5">
                  <dt className="flex items-center gap-1.5 text-xs text-ink-500"><Icon className="h-3.5 w-3.5" />{k}</dt>
                  <dd className="num mt-0.5 font-bold text-ink-900">{v}</dd>
                </div>
              ))}
            </dl>
          </div>
          <div className="flex flex-col justify-center gap-3 border-t border-ink-100 bg-brand-50/50 p-6 lg:w-72 lg:border-l lg:border-t-0">
            <Button size="lg" onClick={() => setIntro(true)} disabled={!readiness.ready_questions}>
              <Play className="h-4 w-4" /> Start mock test
            </Button>
            {readiness.is_ready ? (
              <p className="text-center text-xs text-ink-500">Timer starts when you begin.</p>
            ) : readiness.ready_questions ? (
              <p className="text-center text-xs text-amber-700">
                The question bank is still growing ({readiness.ready_questions}/{readiness.paper_size}). You can still take a shorter test.
              </p>
            ) : (
              <p className="text-center text-xs text-ink-500">Mock tests unlock once questions are added.</p>
            )}
          </div>
        </div>
      </Card>

      <div className="mb-4 flex items-end justify-between">
        <div>
          <h2 className="text-lg font-bold text-ink-900">Syllabus</h2>
          <p className="text-sm text-ink-500">{course.chapters.length} chapters · {course.chapters.reduce((n, c) => n + c.topics.length, 0)} topics</p>
        </div>
        <button className="text-sm font-semibold text-brand-600 hover:underline"
          onClick={() => setOpen(allOpen ? {} : Object.fromEntries(course.chapters.map((c) => [c.id, true])))}>
          {allOpen ? 'Collapse all' : 'Expand all'}
        </button>
      </div>

      {course.chapters.length === 0 && <Notice icon={Info}>The syllabus for this course has not been added yet.</Notice>}

      <div className="space-y-8">
      {groups.map((group) => (
      <section key={group.paper || 'all'}>
        {group.paper && (
          <div className="mb-3 flex items-center gap-3">
            <span className="rounded-lg bg-ink-900 px-2.5 py-1 text-xs font-bold uppercase tracking-wide text-white">{paperShort(group.paper)}</span>
            <h3 className="min-w-0 truncate font-semibold text-ink-800">{group.paper.replace(/^(paper|part)\s+[ivx\d]+\s*[:—–-]?\s*/i, '')}</h3>
            <span className="ml-auto whitespace-nowrap text-xs text-ink-500">{group.chapters.reduce((n, c) => n + (neededByChapter[c.id]?.needed || c.weight || 0), 0)} MCQs</span>
          </div>
        )}
      <div className="space-y-3">
        {group.chapters.map((ch) => {
          const i = course.chapters.indexOf(ch)
          const isOpen = open[ch.id]
          const practised = ch.topics.filter((t) => progress[t.id])
          const avg = practised.length ? Math.round(practised.reduce((s, t) => s + progress[t.id].avg_percent, 0) / practised.length) : null
          const qCount = ch.topics.reduce((n, t) => n + t.question_count, 0)
          return (
            <Card key={ch.id} className="overflow-hidden">
              <button onClick={() => setOpen((o) => ({ ...o, [ch.id]: !o[ch.id] }))}
                className="flex w-full items-center gap-4 px-5 py-4 text-left hover:bg-ink-50/70">
                <span className="num grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-ink-100 text-sm font-bold text-ink-700">{i + 1}</span>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold text-ink-900">{ch.name}</p>
                  <p className="text-xs text-ink-500">
                    {ch.topics.length} topics · {qCount} questions
                    {neededByChapter[ch.id]?.needed ? ` · ${neededByChapter[ch.id].needed} MCQ in the paper` : ''}
                  </p>
                </div>
                {avg !== null && <span className={cx('num hidden text-sm font-bold sm:block', scoreTone(avg))}>{avg}%</span>}
                <ChevronDown className={cx('h-5 w-5 text-ink-400 transition', isOpen && 'rotate-180')} />
              </button>
              {isOpen && (
                <ul className="divide-y divide-ink-100 border-t border-ink-100">
                  {ch.topics.map((t) => {
                    const p = progress[t.id]
                    return (
                      <li key={t.id}>
                        <Link to={`/topics/${t.id}`} className="group flex items-center gap-4 px-5 py-3 hover:bg-brand-50/40">
                          <div className="min-w-0 flex-1 pl-0 sm:pl-[52px]">
                            <p className="text-sm font-medium text-ink-800 group-hover:text-brand-700">{t.name}</p>
                            {t.description && <p className="truncate text-xs text-ink-500">{t.description}</p>}
                          </div>
                          {p ? (
                            <div className="hidden w-32 sm:block">
                              <ProgressBar value={p.avg_percent} />
                              <p className="mt-1 text-right text-[11px] text-ink-500">{p.attempts} quiz{p.attempts > 1 ? 'zes' : ''} · {p.avg_percent}%</p>
                            </div>
                          ) : (
                            <Badge tone={t.question_count ? 'blue' : 'slate'}>{t.question_count ? `${t.question_count} Qs` : 'Coming soon'}</Badge>
                          )}
                          <ArrowRight className="h-4 w-4 text-ink-300 group-hover:text-brand-600" />
                        </Link>
                      </li>
                    )
                  })}
                </ul>
              )}
            </Card>
          )
        })}
      </div>
      </section>
      ))}
      </div>
      {pastPapers.length > 0 && (
        <section className="mt-10">
          <h2 className="mb-1 text-lg font-bold text-ink-900">Past papers</h2>
          <p className="mb-4 text-sm text-ink-500">Official and previous-year papers. Their MCQs are part of the question bank.</p>
          <Card className="divide-y divide-ink-100">
            {pastPapers.map((x) => (
              <div key={x.id} className="flex items-center gap-4 px-5 py-3">
                <span className="num w-12 shrink-0 text-sm font-bold text-ink-500">{x.year || '—'}</span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-ink-800">{x.title.replace(/^(PSC|NRB|Web) · /, '')}</p>
                  <p className="text-xs text-ink-500">
                    {{ psc: 'Lok Sewa Aayog', nrb: 'Nepal Rastra Bank', web: 'Web', upload: 'Uploaded' }[x.source]}
                    {x.status === 'done' && x.mcq_added ? ` · ${x.mcq_added} MCQs in the bank` : x.status === 'no_mcq' ? ' · subjective paper' : ''}
                  </p>
                </div>
                <PaperLink paper={x} className="text-sm" />
              </div>
            ))}
          </Card>
        </section>
      )}

      <ExamIntro course={course} readiness={readiness} open={intro} onClose={() => setIntro(false)} />
    </>
  )
}
