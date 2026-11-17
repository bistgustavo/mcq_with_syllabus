import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { AlertTriangle, Bookmark, Check, ChevronLeft, ChevronRight, Clock3, Cloud, CloudOff, Eraser, Grid3x3, Send, X } from 'lucide-react'
import { api } from '../api/client'
import { useBranding } from '../context/BrandingContext'
import { useToast } from '../context/ToastContext'
import { Button, ConfirmModal, ErrorBox, Spinner, cx } from '../components/ui'
import { LETTERS } from '../utils/format'
import { parseDate } from '../utils/format'

function useCountdown(endsAt, offsetMs) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 500)
    return () => clearInterval(id)
  }, [])
  if (!endsAt) return 0
  return Math.max(0, Math.floor((endsAt - (now + offsetMs)) / 1000))
}

const fmt = (s) => {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  return `${h ? `${h}:` : ''}${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

function cellTone(i, answers, flagged, visited) {
  const answered = answers[i] !== null && answers[i] !== undefined
  if (flagged.has(i)) return 'bg-amber-400 text-amber-950'
  if (answered) return 'bg-emerald-500 text-white'
  if (visited.has(i)) return 'border border-rose-300 bg-rose-50 text-rose-700'
  return 'bg-ink-100 text-ink-600 hover:bg-ink-200'
}

/** Always-visible strip of question numbers (phones and tablets): tap any number to jump. */
function NumberStrip({ questions, answers, flagged, visited, index, onJump }) {
  const ref = useRef(null)
  useEffect(() => {
    const el = ref.current?.querySelector(`[data-n="${index}"]`)
    el?.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' })
  }, [index])
  return (
    <div ref={ref} className="flex gap-1 overflow-x-auto px-4 py-2 [scrollbar-width:thin]">
      {questions.map((q, i) => (
        <button key={q.id} data-n={i} onClick={() => onJump(i)} aria-label={`Question ${i + 1}`}
          className={cx('num h-8 min-w-[2rem] shrink-0 rounded-md px-1 text-[11px] font-bold', cellTone(i, answers, flagged, visited),
            i === index && 'ring-2 ring-brand-600 ring-offset-1')}>
          {i + 1}
        </button>
      ))}
    </div>
  )
}

function JumpTo({ total, onJump }) {
  const [value, setValue] = useState('')
  return (
    <form className="flex items-center gap-1.5" onSubmit={(e) => {
      e.preventDefault()
      const n = parseInt(value, 10)
      if (n >= 1 && n <= total) onJump(n - 1)
      setValue('')
    }}>
      <input value={value} onChange={(e) => setValue(e.target.value.replace(/\D/g, ''))} inputMode="numeric"
        placeholder={`Go to 1–${total}`} aria-label="Go to question number"
        className="num h-8 w-28 rounded-lg border-0 px-2 text-xs ring-1 ring-inset ring-ink-200 focus:ring-2 focus:ring-brand-500" />
      <button type="submit" className="h-8 rounded-lg bg-ink-900 px-2.5 text-xs font-semibold text-white">Go</button>
    </form>
  )
}

const shortPaper = (p) => (p ? (p.match(/^((?:paper|part)\s+[ivx\d]+)/i)?.[1] || p) : 'Questions')

/** Sections of the paper (one per exam paper when several are taken together). */
function sectionOf(sections, i) {
  return Math.max(0, sections.findIndex((s) => i >= s.start && i < s.start + s.count))
}

/**
 * Section tabs for multi-paper exams: jump to a paper, see its progress, and keep to the
 * time split (each paper has its own share of the single shared timer).
 */
function SectionBar({ sections, answers, index, elapsed, onJump }) {
  if (sections.length < 2) return null
  const current = sectionOf(sections, index)
  let cumulative = 0
  return (
    <div className="flex gap-2 overflow-x-auto px-4 py-2">
      {sections.map((s, n) => {
        cumulative += s.minutes * 60
        const done = answers.slice(s.start, s.start + s.count).filter((a) => a !== null && a !== undefined).length
        const active = n === current
        const over = active && elapsed > cumulative
        return (
          <button key={n} onClick={() => onJump(s.start)}
            className={cx('flex shrink-0 items-center gap-2 rounded-xl border px-3 py-1.5 text-left text-xs transition',
              active ? 'border-brand-500 bg-brand-50 ring-1 ring-brand-500' : 'border-ink-200 bg-white hover:border-ink-300')}>
            <span className="font-bold text-ink-900">{shortPaper(s.paper)}</span>
            <span className="num text-ink-500">Q{s.start + 1}–{s.start + s.count}</span>
            <span className={cx('num rounded-md px-1.5 py-0.5 font-semibold', done === s.count ? 'bg-emerald-100 text-emerald-700' : 'bg-ink-100 text-ink-600')}>
              {done}/{s.count}
            </span>
            <span className={cx('num', over ? 'font-semibold text-amber-700' : 'text-ink-400')}>
              {over ? `over ${s.minutes} min` : `${s.minutes} min`}
            </span>
          </button>
        )
      })}
    </div>
  )
}

function Palette({ questions, answers, flagged, visited, index, onJump, sections = [] }) {
  const counts = {
    answered: answers.filter((a) => a !== null && a !== undefined).length,
    flagged: flagged.size,
    notVisited: questions.length - visited.size,
  }
  return (
    <div>
      <div className="grid grid-cols-2 gap-2 text-xs text-ink-600">
        <span className="flex items-center gap-2"><span className="h-4 w-4 rounded bg-emerald-500" /> Answered ({counts.answered})</span>
        <span className="flex items-center gap-2"><span className="h-4 w-4 rounded bg-amber-400" /> For review ({counts.flagged})</span>
        <span className="flex items-center gap-2"><span className="h-4 w-4 rounded border border-rose-300 bg-rose-50" /> Not answered</span>
        <span className="flex items-center gap-2"><span className="h-4 w-4 rounded bg-ink-100" /> Not visited ({counts.notVisited})</span>
      </div>
      <div className="mt-4 grid max-h-[46vh] grid-cols-8 gap-1 overflow-y-auto pr-1 sm:grid-cols-10 lg:grid-cols-7">
        {questions.flatMap((q, i) => {
          const header = sections.length > 1 && sections.find((s) => s.start === i)
          const answered = answers[i] !== null && answers[i] !== undefined
          const isFlagged = flagged.has(i)
          const cell = (
            <button key={q.id} onClick={() => onJump(i)}
              className={cx(
                'num relative h-8 rounded-md text-[11px] font-bold transition',
                i === index && 'ring-2 ring-brand-600 ring-offset-1',
                isFlagged ? 'bg-amber-400 text-amber-950'
                  : answered ? 'bg-emerald-500 text-white'
                  : visited.has(i) ? 'border border-rose-300 bg-rose-50 text-rose-700'
                  : 'bg-ink-100 text-ink-600 hover:bg-ink-200',
              )}
              aria-label={`Question ${i + 1}`}>
              {i + 1}
              {isFlagged && answered && <span className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full border-2 border-white bg-emerald-500" />}
            </button>
          )
          return header
            ? [<p key={`h${i}`} className="col-span-full mt-2 text-[11px] font-bold uppercase tracking-wide text-ink-500 first:mt-0">
                {shortPaper(header.paper)} · Q{header.start + 1}–{header.start + header.count}
              </p>, cell]
            : [cell]
        })}
      </div>
    </div>
  )
}

export default function ExamPage() {
  const { examId } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const { branding } = useBranding()

  const [exam, setExam] = useState(null)
  const [error, setError] = useState(null)
  const [answers, setAnswers] = useState([])
  const [flagged, setFlagged] = useState(new Set())
  const [visited, setVisited] = useState(new Set([0]))
  const [index, setIndex] = useState(0)
  const [offsetMs, setOffsetMs] = useState(0)
  const [saveState, setSaveState] = useState('saved') // saved | saving | offline
  const [confirm, setConfirm] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [paletteOpen, setPaletteOpen] = useState(false)
  const dirty = useRef(false)
  const submittedRef = useRef(false)

  useEffect(() => {
    api.exam(examId).then((e) => {
      setExam(e)
      setAnswers(e.answers)
      setFlagged(new Set(e.flagged))
      setVisited(new Set([0, ...e.answers.map((a, i) => (a !== null ? i : null)).filter((i) => i !== null)]))
      setOffsetMs(parseDate(e.server_now).getTime() - Date.now())
    }).catch(setError)
  }, [examId])

  const endsAt = exam ? parseDate(exam.ends_at).getTime() : null
  const remaining = useCountdown(endsAt, offsetMs)

  // ---- autosave (debounced) -------------------------------------------------
  const save = useCallback(async () => {
    if (!dirty.current || submittedRef.current) return
    dirty.current = false
    setSaveState('saving')
    try {
      await api.saveExam(examId, { answers, flagged: [...flagged] })
      setSaveState('saved')
    } catch {
      dirty.current = true
      setSaveState('offline')
    }
  }, [answers, flagged, examId])

  useEffect(() => {
    if (!exam) return undefined
    const id = setTimeout(save, 1200)
    return () => clearTimeout(id)
  }, [answers, flagged, save, exam])

  useEffect(() => {
    const warn = (e) => {
      if (!submittedRef.current) {
        e.preventDefault()
        e.returnValue = ''
      }
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [])

  const submit = useCallback(async (auto = false) => {
    if (submittedRef.current) return
    submittedRef.current = true
    setSubmitting(true)
    try {
      await api.submitExam(examId, { answers, flagged: [...flagged] })
      if (auto) toast.info('Time is up. Your exam was submitted automatically.')
      navigate(`/exam/${examId}/result`, { replace: true })
    } catch (err) {
      submittedRef.current = false
      setSubmitting(false)
      toast.error(err.message)
    }
  }, [answers, flagged, examId, navigate, toast])

  useEffect(() => {
    if (exam && exam.status === 'in_progress' && remaining === 0) submit(true)
  }, [remaining, exam, submit])

  const questions = useMemo(() => exam?.questions || [], [exam])
  const q = questions[index]

  const go = useCallback((i) => {
    const next = Math.max(0, Math.min(questions.length - 1, i))
    setIndex(next)
    setVisited((v) => new Set(v).add(next))
    setPaletteOpen(false)
  }, [questions.length])

  const choose = useCallback((opt) => {
    dirty.current = true
    setAnswers((a) => a.map((v, i) => (i === index ? opt : v)))
  }, [index])

  const toggleFlag = () => {
    dirty.current = true
    setFlagged((f) => {
      const n = new Set(f)
      if (n.has(index)) n.delete(index)
      else n.add(index)
      return n
    })
  }

  useEffect(() => {
    const onKey = (e) => {
      if (!q || confirm) return
      const k = e.key.toUpperCase()
      const n = ['1', '2', '3', '4'].indexOf(k)
      const choice = n >= 0 ? n : LETTERS.indexOf(k)
      if (choice >= 0) choose(choice)
      if (e.key === 'ArrowRight') go(index + 1)
      if (e.key === 'ArrowLeft') go(index - 1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [q, index, choose, go, confirm])

  if (error) return <div className="mx-auto max-w-lg p-10"><ErrorBox error={error} /></div>
  if (!exam) return <Spinner label="Loading your exam…" className="min-h-screen" />
  if (exam.status === 'submitted') return <Navigate to={`/exam/${examId}/result`} replace />

  const answeredCount = answers.filter((a) => a !== null && a !== undefined).length
  const sections = exam.sections || []
  const elapsed = exam.time_limit_seconds - remaining
  const currentSection = sections[sectionOf(sections, index)]
  const low = remaining <= 300
  const neg = Math.round(exam.negative_marking * 100)

  return (
    <div className="flex min-h-screen flex-col bg-ink-50">
      {/* top bar */}
      <header className="sticky top-0 z-20 border-b border-ink-200 bg-white">
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-4 px-4">
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-medium text-ink-500">{branding.institution_name} · Mock test{exam.paper ? ` · ${exam.paper}` : ''}</p>
            <p className="truncate font-semibold text-ink-900">{exam.exam_name}</p>
          </div>
          <span className={cx('hidden items-center gap-1.5 text-xs sm:flex', saveState === 'offline' ? 'text-rose-600' : 'text-ink-400')}>
            {saveState === 'offline' ? <CloudOff className="h-4 w-4" /> : <Cloud className="h-4 w-4" />}
            {saveState === 'saving' ? 'Saving…' : saveState === 'offline' ? 'Not saved, retrying' : 'All answers saved'}
          </span>
          <div className={cx('num flex items-center gap-2 rounded-xl px-3 py-2 font-mono text-lg font-bold',
            low ? 'animate-pulse bg-rose-600 text-white' : 'bg-ink-900 text-white')} aria-live="polite">
            <Clock3 className="h-4 w-4" /> {fmt(remaining)}
          </div>
          <Button variant="accent" onClick={() => setConfirm(true)} className="hidden sm:inline-flex"><Send className="h-4 w-4" /> Submit</Button>
        </div>
      </header>

      {sections.length > 1 && (
        <div className="border-b border-ink-200 bg-ink-50">
          <div className="mx-auto max-w-7xl">
            <SectionBar sections={sections} answers={answers} index={index} elapsed={elapsed} onJump={go} />
          </div>
        </div>
      )}
      <div className="sticky top-16 z-10 border-b border-ink-200 bg-white/95 backdrop-blur lg:hidden">
        <NumberStrip questions={questions} answers={answers} flagged={flagged} visited={visited} index={index} onJump={go} />
      </div>

      <div className="mx-auto grid w-full max-w-7xl flex-1 gap-6 px-4 py-6 lg:grid-cols-[1fr_340px]">
        {/* question */}
        <main className="min-w-0">
          <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
            <span className="num rounded-lg bg-brand-600 px-2.5 py-1 font-bold text-white">Q {index + 1} / {questions.length}</span>
            {sections.length > 1 && currentSection && (
              <span className="rounded-lg bg-ink-900 px-2.5 py-1 text-xs font-semibold text-white">{currentSection.paper}</span>
            )}
            <span className="rounded-lg bg-white px-2.5 py-1 text-ink-600 ring-1 ring-ink-200">{q.chapter_name}</span>
            <span className="ml-auto hidden text-xs text-ink-500 sm:inline">+1 correct · −{exam.negative_marking} wrong</span>
            <span className="ml-auto lg:hidden sm:ml-2"><JumpTo total={questions.length} onJump={go} /></span>
          </div>
          <div className="rounded-2xl border border-ink-200 bg-white p-6 shadow-card sm:p-8">
            <h1 className="text-lg font-semibold leading-relaxed text-ink-900 sm:text-xl">{q.question_text}</h1>
            <div className="mt-7 space-y-3">
              {q.options.map((opt, i) => {
                const sel = answers[index] === i
                return (
                  <button key={i} onClick={() => choose(i)}
                    className={cx('flex w-full items-start gap-4 rounded-xl border-2 px-4 py-3.5 text-left transition',
                      sel ? 'border-brand-600 bg-brand-50' : 'border-ink-200 hover:border-ink-300 hover:bg-ink-50')}>
                    <span className={cx('grid h-8 w-8 shrink-0 place-items-center rounded-lg text-sm font-bold',
                      sel ? 'bg-brand-600 text-white' : 'bg-ink-100 text-ink-600')}>
                      {sel ? <Check className="h-4 w-4" /> : LETTERS[i]}
                    </span>
                    <span className="pt-1 text-[15px] text-ink-800">{opt}</span>
                  </button>
                )
              })}
            </div>
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-2">
            <Button variant="secondary" onClick={() => go(index - 1)} disabled={index === 0}><ChevronLeft className="h-4 w-4" /> Previous</Button>
            <Button variant="secondary" onClick={toggleFlag}
              className={flagged.has(index) ? '!bg-amber-50 !text-amber-800 !ring-amber-300' : ''}>
              <Bookmark className={cx('h-4 w-4', flagged.has(index) && 'fill-amber-400')} /> {flagged.has(index) ? 'Marked for review' : 'Mark for review'}
            </Button>
            <Button variant="ghost" onClick={() => choose(null)} disabled={answers[index] === null}><Eraser className="h-4 w-4" /> Clear</Button>
            <div className="ml-auto flex gap-2">
              <Button variant="secondary" className="lg:hidden" onClick={() => setPaletteOpen(true)}><Grid3x3 className="h-4 w-4" /></Button>
              {index < questions.length - 1 ? (
                <Button onClick={() => go(index + 1)}>Save & next <ChevronRight className="h-4 w-4" /></Button>
              ) : (
                <Button variant="accent" onClick={() => setConfirm(true)}><Send className="h-4 w-4" /> Submit</Button>
              )}
            </div>
          </div>
          <p className="mt-4 hidden text-xs text-ink-400 sm:block">Keyboard: 1–4 or A–D to answer · ← → to move</p>
        </main>

        {/* palette */}
        <aside className="hidden lg:block">
          <div className="sticky top-24 rounded-2xl border border-ink-200 bg-white p-5 shadow-card">
            <div className="mb-4 flex items-center justify-between gap-2">
              <p className="font-semibold text-ink-900">All {questions.length} questions</p>
              <JumpTo total={questions.length} onJump={go} />
            </div>
            <Palette questions={questions} answers={answers} flagged={flagged} visited={visited} index={index} onJump={go} sections={sections} />
            <div className="mt-5 rounded-xl bg-ink-50 p-3 text-xs leading-relaxed text-ink-600">
              <p className="flex items-center gap-1.5 font-semibold text-ink-800"><AlertTriangle className="h-3.5 w-3.5 text-amber-500" /> Negative marking</p>
              {neg}% of a mark is deducted per wrong answer. Unanswered questions score zero.
            </div>
            <Button variant="accent" className="mt-4 w-full" onClick={() => setConfirm(true)}><Send className="h-4 w-4" /> Submit exam</Button>
          </div>
        </aside>
      </div>

      {paletteOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-ink-950/40" onClick={() => setPaletteOpen(false)} />
          <div className="absolute inset-x-0 bottom-0 max-h-[75vh] animate-fade-up overflow-y-auto rounded-t-3xl bg-white p-5">
            <div className="mb-4 flex items-center justify-between">
              <p className="font-semibold text-ink-900">Question palette</p>
              <button onClick={() => setPaletteOpen(false)} className="rounded-lg p-1 text-ink-400" aria-label="Close"><X className="h-5 w-5" /></button>
            </div>
            <Palette questions={questions} answers={answers} flagged={flagged} visited={visited} index={index} onJump={go} sections={sections} />
            <Button variant="accent" className="mt-5 w-full" onClick={() => { setPaletteOpen(false); setConfirm(true) }}>Submit exam</Button>
          </div>
        </div>
      )}

      <ConfirmModal
        open={confirm}
        title="Submit your exam?"
        variant="accent"
        confirmLabel="Submit now"
        loading={submitting}
        onConfirm={() => submit(false)}
        onClose={() => setConfirm(false)}
        message={
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-2 text-center">
              {[['Answered', answeredCount, 'text-emerald-600'], ['Unanswered', questions.length - answeredCount, 'text-rose-600'], ['For review', flagged.size, 'text-amber-600']].map(([k, v, c]) => (
                <div key={k} className="rounded-xl bg-ink-50 p-3">
                  <p className={cx('num text-2xl font-bold', c)}>{v}</p>
                  <p className="text-xs text-ink-500">{k}</p>
                </div>
              ))}
            </div>
            <p>You still have <strong className="num">{fmt(remaining)}</strong> left. Once submitted, answers can&apos;t be changed.</p>
          </div>
        }
      />
    </div>
  )
}
