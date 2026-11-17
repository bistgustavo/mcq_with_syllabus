import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, Check, ClipboardCheck, Clock3, ListChecks, MinusCircle, Play, Target } from 'lucide-react'
import { api } from '../api/client'
import { useToast } from '../context/ToastContext'
import { useAsync } from '../hooks/useAsync'
import { Badge, Button, Card, CardHeader, EmptyState, ErrorBox, Modal, PageHeader, Skeleton, cx } from '../components/ui'
import { formatDate, paperShort, scoreTone } from '../utils/format'

/** Choose a paper (or the full exam), read the instructions, then start the clock. */
export function ExamIntro({ course, open, onClose, initialPaper = null }) {
  const navigate = useNavigate()
  const toast = useToast()
  const [papers, setPapers] = useState([])
  const [paper, setPaper] = useState(initialPaper)
  const [ready, setReady] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open || !course) return
    setReady(null)
    api.readiness(course.id).then((r) => {
      setPapers(r.papers || [])
      // Multi-paper courses default to the first paper: that is how the real exam is sat.
      setPaper((p) => (p !== null ? p : r.papers?.length ? r.papers[0] : null))
    }).catch(() => {})
  }, [open, course])

  useEffect(() => {
    if (!open || !course) return
    api.readiness(course.id, paper || undefined).then(setReady).catch(() => setReady(null))
  }, [open, course, paper])

  if (!course) return null
  const n = papers.length || 1
  const isFull = !paper
  const size = ready?.paper_size ?? (isFull ? course.exam_question_count * n : course.exam_question_count)
  const minutes = isFull ? course.exam_duration_minutes * n : course.exam_duration_minutes
  const available = ready ? Math.min(ready.ready_questions + 0, size) : null

  const begin = async () => {
    setBusy(true)
    try {
      const exam = await api.startExam(course.id, paper)
      if (exam.fresh_generated > 0) toast.info(`${exam.fresh_generated} new questions were written for this paper by the AI.`)
      navigate(`/exam/${exam.id}`)
    } catch (err) {
      toast.error(err.message)
      setBusy(false)
    }
  }

  const options = [...papers.map((p) => ({ value: p, label: p, q: course.exam_question_count, m: course.exam_duration_minutes })),
    ...(papers.length > 1 ? [{ value: null, label: `All ${papers.length} ${paperShort(papers[0]).split(' ')[0].toLowerCase()}s together: ${papers.length} sections in one sitting (${course.exam_duration_minutes} min each)`, q: course.exam_question_count * n, m: course.exam_duration_minutes * n }] : [])]

  return (
    <Modal open={open} onClose={onClose} title="Before you begin" wide
      footer={<><Button variant="secondary" onClick={onClose}>Not now</Button>
        <Button onClick={begin} loading={busy} disabled={ready && !ready.ready_questions}>
          {busy ? 'Preparing your paper…' : <><Play className="h-4 w-4" /> Start the timer</>}
        </Button></>}>
      <p className="text-sm text-ink-500">{course.exam_name || course.name}</p>

      {options.length > 1 && (
        <div className="mt-4 space-y-2">
          {options.map((o) => {
            const active = paper === o.value
            return (
              <button key={o.label} onClick={() => setPaper(o.value)}
                className={cx('flex w-full items-center gap-3 rounded-xl border px-4 py-3 text-left transition',
                  active ? 'border-brand-500 bg-brand-50 ring-1 ring-brand-500' : 'border-ink-200 hover:border-ink-300')}>
                <span className={cx('grid h-5 w-5 shrink-0 place-items-center rounded-full border', active ? 'border-brand-600 bg-brand-600 text-white' : 'border-ink-300')}>
                  {active && <Check className="h-3 w-3" />}
                </span>
                <span className="min-w-0 flex-1 text-sm font-semibold text-ink-900">{o.label}</span>
                <span className="num whitespace-nowrap text-xs text-ink-500">{o.q} Q · {o.m} min</span>
              </button>
            )
          })}
        </div>
      )}

      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[[ListChecks, 'Questions', size], [Clock3, 'Duration', `${minutes} min`],
          [MinusCircle, 'Negative', `${course.negative_marking} / wrong`], [Target, 'Pass mark', `${course.pass_percent}%`]].map(([Icon, k, v]) => (
          <div key={k} className="rounded-xl bg-ink-50 p-3">
            <p className="flex items-center gap-1.5 text-xs text-ink-500"><Icon className="h-3.5 w-3.5" /> {k}</p>
            <p className="num mt-0.5 text-lg font-bold text-ink-900">{v}</p>
          </div>
        ))}
      </div>
      {busy && (
        <p className="mt-3 rounded-lg bg-brand-50 px-3 py-2 text-xs text-brand-800">
          Assembling your paper. If you have already seen the available questions, the AI is writing new ones from the syllabus. This can take up to a minute.
        </p>
      )}
      {ready && !ready.is_ready && (
        <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
          {ready.ready_questions
            ? `The bank has ${available} of ${size} questions ready for this paper; the AI writes the rest from the syllabus when you start.`
            : 'No questions are available for this paper yet.'}
        </p>
      )}
      {ready?.marking && (
        <div className="mt-4 rounded-xl bg-brand-50/60 p-4 text-sm text-ink-800">
          <p className="mb-1.5 font-semibold text-ink-900">Marking scheme (from the syllabus)</p>
          <ul className="space-y-0.5">{ready.marking.lines.map((l) => <li key={l}>• {l}</li>)}</ul>
        </div>
      )}
      <div className="mt-4 rounded-xl border border-ink-200 p-4 text-sm leading-relaxed text-ink-700">
        <p className="mb-2 font-semibold text-ink-900">Instructions</p>
        <div className="whitespace-pre-line">
          {course.exam_instructions ||
            `• Each correct answer earns 1 mark; ${course.negative_marking} mark is deducted for each wrong answer.\n• Your answers are saved automatically.\n• The exam submits itself when the timer reaches zero.`}
        </div>
      </div>
    </Modal>
  )
}

export default function MockTests() {
  const { data, error, loading, reload } = useAsync(
    () => Promise.all([api.courses(), api.myExams()]).then(async ([courses, exams]) => ({
      courses,
      exams,
      readiness: Object.fromEntries(await Promise.all(courses.map((c) => api.readiness(c.id).then((r) => [c.id, r])))),
    })),
    [],
  )
  const [intro, setIntro] = useState(null)

  if (loading && !data) return <div className="space-y-4"><Skeleton className="h-40" /><Skeleton className="h-64" /></div>
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!data) return null
  const { courses, exams, readiness } = data

  return (
    <>
      <PageHeader eyebrow="Exam practice" title="Mock tests" subtitle="Timed papers that follow the real exam pattern, negative marking included. Take one paper or the full exam." />

      {courses.length === 0 && <EmptyState icon={ClipboardCheck} title="No courses yet" />}
      <div className="mb-10 grid gap-5 md:grid-cols-2">
        {courses.map((c) => {
          const r = readiness[c.id]
          const papers = r?.papers || []
          const running = exams.filter((e) => e.course_id === c.id && e.status === 'in_progress')
          const mine = exams.filter((e) => e.course_id === c.id && e.status === 'submitted')
          const best = mine.length ? Math.max(...mine.map((e) => e.percent)) : null
          return (
            <Card key={c.id} className="flex flex-col overflow-hidden">
              <div className="bg-gradient-to-br from-brand-600 to-brand-800 p-6 text-white">
                <p className="text-xs font-semibold text-brand-100">{c.exam_name || 'Mock test'}</p>
                <h2 className="mt-1 text-xl font-bold">{c.name}</h2>
                <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 text-sm text-brand-50">
                  {papers.length > 1 ? <span>{papers.length} papers · {c.exam_question_count} Q / {c.exam_duration_minutes} min each</span>
                    : <span>{c.exam_question_count} questions · {c.exam_duration_minutes} minutes</span>}
                  <span>−{c.negative_marking} per wrong</span>
                </div>
              </div>
              {papers.length > 1 && (
                <div className="flex flex-wrap gap-2 border-b border-ink-100 px-5 py-3">
                  {papers.map((p) => <Badge key={p} tone="blue">{paperShort(p)}</Badge>)}
                  <Badge>Full exam</Badge>
                </div>
              )}
              <div className="flex flex-1 items-center gap-4 p-5">
                <div className="flex-1 text-sm">
                  <p className="text-ink-500">Attempts: <strong className="text-ink-900">{mine.length}</strong></p>
                  <p className="text-ink-500">Best: <strong className={best === null ? 'text-ink-900' : scoreTone(best)}>{best === null ? '—' : `${best}%`}</strong></p>
                </div>
                {running.length > 0 && (
                  <Link to={`/exam/${running[0].id}`}><Button variant="accent">Resume <ArrowRight className="h-4 w-4" /></Button></Link>
                )}
                <Button onClick={() => setIntro(c)} disabled={!r?.ready_questions} variant={running.length ? 'secondary' : 'primary'}>
                  <Play className="h-4 w-4" /> Start test
                </Button>
              </div>
            </Card>
          )
        })}
      </div>

      <Card>
        <CardHeader icon={ClipboardCheck} title="Your attempts" />
        {exams.length === 0 ? (
          <p className="px-5 py-10 text-center text-sm text-ink-500">No mock tests taken yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-ink-500">
                <tr><th className="px-5 py-3">Date</th><th className="px-5 py-3">Course</th><th className="px-5 py-3">Paper</th><th className="px-5 py-3">Score</th><th className="px-5 py-3">✓ / ✗ / –</th><th className="px-5 py-3">Result</th><th /></tr>
              </thead>
              <tbody className="divide-y divide-ink-100">
                {exams.map((e) => (
                  <tr key={e.id} className="hover:bg-ink-50">
                    <td className="px-5 py-3 text-ink-600">{formatDate(e.submitted_at || e.started_at)}</td>
                    <td className="px-5 py-3 font-medium text-ink-900">{e.course_name}</td>
                    <td className="px-5 py-3"><Badge tone={e.paper ? 'blue' : 'slate'}>{paperShort(e.paper)}</Badge></td>
                    <td className={cx('num px-5 py-3 font-bold', e.status === 'submitted' && scoreTone(e.percent))}>
                      {e.status === 'submitted' ? `${e.score}/${e.total} · ${e.percent}%` : '—'}
                    </td>
                    <td className="num px-5 py-3 text-ink-600">{e.status === 'submitted' ? `${e.correct} / ${e.wrong} / ${e.skipped}` : '—'}</td>
                    <td className="px-5 py-3">
                      {e.status !== 'submitted' ? <Badge tone="violet">In progress</Badge> : e.passed ? <Badge tone="green">Pass</Badge> : <Badge tone="red">Below pass</Badge>}
                    </td>
                    <td className="px-5 py-3 text-right">
                      <Link to={e.status === 'submitted' ? `/exam/${e.id}/result` : `/exam/${e.id}`} className="font-semibold text-brand-600 hover:underline">
                        {e.status === 'submitted' ? 'Review' : 'Resume'}
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <ExamIntro course={intro} open={Boolean(intro)} onClose={() => setIntro(null)} />
    </>
  )
}
