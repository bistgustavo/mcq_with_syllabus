import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Check, ChevronLeft, ChevronRight, Clock3, Send } from 'lucide-react'
import { api } from '../api/client'
import { useToast } from '../context/ToastContext'
import { useAsync } from '../hooks/useAsync'
import { Button, ConfirmModal, DifficultyBadge, EmptyState, ErrorBox, Spinner, cx } from '../components/ui'
import { LETTERS, formatDuration } from '../utils/format'

export default function QuizPage() {
  const { topicId } = useParams()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const toast = useToast()
  const count = Number(params.get('count') || 10)
  const difficulty = params.get('difficulty') || undefined

  const { data: quiz, error, loading, reload } = useAsync(() => api.startQuiz(topicId, { count, difficulty }), [topicId, count, difficulty])
  const [answers, setAnswers] = useState({})
  const [index, setIndex] = useState(0)
  const [elapsed, setElapsed] = useState(0)
  const [confirm, setConfirm] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const startedAt = useRef(Date.now())

  useEffect(() => {
    startedAt.current = Date.now()
    const id = setInterval(() => setElapsed(Math.round((Date.now() - startedAt.current) / 1000)), 1000)
    return () => clearInterval(id)
  }, [quiz])

  const questions = useMemo(() => quiz?.questions || [], [quiz])
  const answered = Object.keys(answers).length
  const current = questions[index]

  useEffect(() => {
    const onKey = (e) => {
      if (!current || confirm) return
      const key = e.key.toUpperCase()
      const n = ['1', '2', '3', '4'].indexOf(key)
      const choice = n >= 0 ? n : LETTERS.indexOf(key)
      if (choice >= 0) setAnswers((a) => ({ ...a, [current.id]: choice }))
      if (e.key === 'ArrowRight') setIndex((i) => Math.min(i + 1, questions.length - 1))
      if (e.key === 'ArrowLeft') setIndex((i) => Math.max(i - 1, 0))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [current, questions.length, confirm])

  const submit = async () => {
    setSubmitting(true)
    try {
      const result = await api.submitQuiz({
        topic_id: Number(topicId),
        difficulty: difficulty || null,
        duration_seconds: elapsed,
        answers: questions.map((q) => ({ question_id: q.id, selected_index: answers[q.id] ?? null })),
      })
      navigate(`/attempts/${result.attempt_id}`, { replace: true })
    } catch (err) {
      toast.error(err.message)
      setSubmitting(false)
      setConfirm(false)
    }
  }

  if (loading && !quiz) return <Spinner label="Preparing your quiz…" />
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!questions.length) {
    return <EmptyState title="No questions available yet" action={<Link to={`/topics/${topicId}`}><Button>Back to topic</Button></Link>} />
  }

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-5 flex items-center justify-between gap-4">
        <div className="min-w-0">
          <Link to={`/topics/${topicId}`} className="text-sm text-ink-500 hover:text-ink-800">← {quiz.topic_name}</Link>
          <p className="mt-0.5 text-sm font-semibold text-ink-800">Question {index + 1} of {questions.length} · {answered} answered</p>
        </div>
        <span className="num flex items-center gap-1.5 rounded-xl bg-white px-3 py-1.5 font-mono text-sm font-semibold text-ink-700 ring-1 ring-ink-200">
          <Clock3 className="h-4 w-4" /> {formatDuration(elapsed)}
        </span>
      </div>
      {(quiz.fresh_generated > 0 || quiz.repeats > 0) && (
        <p className="mb-4 rounded-xl bg-brand-50 px-4 py-2.5 text-sm text-brand-800">
          {quiz.fresh_generated > 0 && `✨ ${quiz.fresh_generated} new question${quiz.fresh_generated > 1 ? 's were' : ' was'} written for you just now. `}
          {quiz.repeats > 0 && `${quiz.repeats} question${quiz.repeats > 1 ? 's' : ''} you've seen before ${quiz.repeats > 1 ? 'are' : 'is'} included for revision.`}
        </p>
      )}
      <div className="mb-6 h-1.5 overflow-hidden rounded-full bg-ink-200">
        <div className="h-full rounded-full bg-brand-600 transition-all" style={{ width: `${(answered / questions.length) * 100}%` }} />
      </div>

      <div className="rounded-2xl border border-ink-200 bg-white p-6 shadow-card sm:p-8">
        <DifficultyBadge value={current.difficulty} />
        <h2 className="mt-4 text-lg font-semibold leading-relaxed text-ink-900 sm:text-xl">{current.question_text}</h2>
        <div className="mt-7 space-y-3">
          {current.options.map((opt, i) => {
            const selected = answers[current.id] === i
            return (
              <button key={i} onClick={() => setAnswers((a) => ({ ...a, [current.id]: i }))}
                className={cx('flex w-full items-start gap-4 rounded-xl border-2 px-4 py-3.5 text-left transition',
                  selected ? 'border-brand-600 bg-brand-50' : 'border-ink-200 hover:border-ink-300 hover:bg-ink-50')}>
                <span className={cx('grid h-8 w-8 shrink-0 place-items-center rounded-lg text-sm font-bold', selected ? 'bg-brand-600 text-white' : 'bg-ink-100 text-ink-600')}>
                  {selected ? <Check className="h-4 w-4" /> : LETTERS[i]}
                </span>
                <span className="pt-1 text-[15px] text-ink-800">{opt}</span>
              </button>
            )
          })}
        </div>
      </div>

      <div className="mt-6 flex items-center justify-between gap-2">
        <Button variant="secondary" onClick={() => setIndex((i) => i - 1)} disabled={index === 0}><ChevronLeft className="h-4 w-4" /> Previous</Button>
        {index < questions.length - 1 ? (
          <Button onClick={() => setIndex((i) => i + 1)}>Next <ChevronRight className="h-4 w-4" /></Button>
        ) : (
          <Button onClick={() => setConfirm(true)}><Send className="h-4 w-4" /> Finish</Button>
        )}
      </div>

      <div className="mt-8 flex flex-wrap justify-center gap-1.5">
        {questions.map((q, i) => (
          <button key={q.id} onClick={() => setIndex(i)} aria-label={`Go to question ${i + 1}`}
            className={cx('num h-9 w-9 rounded-lg text-sm font-semibold transition', i === index && 'ring-2 ring-brand-600 ring-offset-2',
              answers[q.id] !== undefined ? 'bg-brand-600 text-white' : 'bg-ink-200/70 text-ink-600 hover:bg-ink-200')}>
            {i + 1}
          </button>
        ))}
      </div>
      <p className="mt-4 text-center text-xs text-ink-400">Press 1–4 or A–D to answer, ← → to move · <button className="font-semibold text-brand-600 hover:underline" onClick={() => setConfirm(true)}>Finish now</button></p>

      <ConfirmModal open={confirm} title="Finish this quiz?" variant="primary" confirmLabel="See my score" loading={submitting}
        onConfirm={submit} onClose={() => setConfirm(false)}
        message={answered < questions.length ? `${questions.length - answered} question(s) are unanswered and will count as wrong.` : 'All questions answered. Ready to see your score?'} />
    </div>
  )
}
