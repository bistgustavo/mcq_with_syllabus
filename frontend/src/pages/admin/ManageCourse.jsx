import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  ArrowDown, ArrowUp, BookMarked, ChevronRight, ClipboardList, Eye, FileText, Globe, History, Layers3, ListChecks, Loader2,
  Pencil, Plus, Rocket, ScanText, Settings2, Sparkles, Trash2, UploadCloud, Wand2,
} from 'lucide-react'
import { api } from '../../api/client'
import { useToast } from '../../context/ToastContext'
import { useAsync, useInterval, useTaskPoller } from '../../hooks/useAsync'
import {
  Badge, Button, Card, CardHeader, ConfirmModal, ErrorBox, Field, Input, Modal, Notice, PageHeader, ProgressBar,
  Skeleton, Tabs, Textarea, Toggle, cx,
} from '../../components/ui'
import { groupByPaper, paperShort, papersOf } from '../../utils/format'
import PastPapers from '../../components/PastPapers'

// --------------------------------------------------------------------------- content pipeline
function BankBuilder({ course, readiness, onDone }) {
  const toast = useToast()
  const [taskId, setTaskId] = useState(null)
  const [status, setStatus] = useState(null)
  const [perTopic, setPerTopic] = useState(15)
  const [research, setResearch] = useState(true)
  const [busy, setBusy] = useState(false)
  const active = (s) => s && ['PENDING', 'STARTED', 'PROGRESS', 'RETRY'].includes(s.state)
  const running = Boolean(taskId) && (!status || active(status))

  // The server remembers the latest job per course, so progress shows on any device.
  useEffect(() => {
    api.bankJob(course.id).then(({ job }) => {
      if (!job) return
      setStatus(job)
      if (active(job)) setTaskId(job.task_id)
    }).catch(() => {})
  }, [course.id])

  const poll = async () => {
    if (!taskId) return
    try {
      const s = await api.task(taskId)
      setStatus(s)
      if (s.state === 'SUCCESS' || s.state === 'FAILURE') {
        setTaskId(null)
        if (s.state === 'SUCCESS') toast.success(`Question bank updated: +${s.result.generated} questions.`)
        else toast.error(s.error || 'The job failed')
        onDone()
      }
    } catch { /* transient */ }
  }
  useInterval(poll, 2500, running)

  const start = async () => {
    setBusy(true)
    try {
      const r = await api.buildBank(course.id, { per_topic: Number(perTopic), research })
      setStatus(null)
      setTaskId(r.task_id)
    } catch (err) {
      toast.error(err.message)
    } finally {
      setBusy(false)
    }
  }

  const p = status?.progress || status?.result
  const pct = p?.total ? Math.round((100 * p.done) / p.total) : 0

  return (
    <Card>
      <CardHeader icon={Wand2} title="Build the question bank"
        subtitle="For every topic: use uploaded PDFs, otherwise research the web by its syllabus text, then write questions at all three levels." />
      <div className="p-5">
        {running ? (
          <div>
            <div className="mb-2 flex items-center justify-between text-sm">
              <span className="flex items-center gap-2 font-medium text-ink-800"><Loader2 className="h-4 w-4 animate-spin text-brand-600" />
                {p?.current ? `Working on: ${p.current}` : 'Starting…'}</span>
              <span className="num text-ink-500">{p ? `${p.done}/${p.total} topics` : ''}</span>
            </div>
            <ProgressBar value={pct} tone="bg-brand-600" className="h-2.5" />
            {p && (
              <div className="mt-3 flex flex-wrap gap-4 text-xs text-ink-600">
                <span>🔎 {p.researched} researched</span><span>✅ {p.generated} questions</span>{p.failed > 0 && <span className="text-rose-600">❌ {p.failed} failed</span>}
              </div>
            )}
            {p?.log?.length > 0 && (
              <pre className="mt-4 max-h-52 overflow-y-auto whitespace-pre-wrap rounded-xl bg-ink-900 p-4 font-mono text-xs leading-relaxed text-ink-200">
                {p.log.slice().reverse().join('\n')}
              </pre>
            )}
            <p className="mt-3 text-xs text-ink-500">You can leave this page. The job keeps running in the background.</p>
          </div>
        ) : (
          <div className="flex flex-col gap-5 sm:flex-row sm:items-end">
            <Field label="Target questions per topic" hint="Split evenly across easy / medium / hard." className="sm:w-56">
              <Input type="number" min={3} max={60} value={perTopic} onChange={(e) => setPerTopic(e.target.value)} />
            </Field>
            <div className="flex-1 pb-1"><Toggle checked={research} onChange={setResearch} label="Research topics without PDFs on the web" description="Uses the topic's syllabus text to stay on-syllabus." /></div>
            <Button onClick={start} loading={busy} size="lg"><Rocket className="h-4 w-4" /> Build now</Button>
          </div>
        )}
        {status?.state === 'SUCCESS' && status.result && !running && (
          <Notice tone="success" className="mt-4" title="Last run finished">
            {status.result.generated} questions added · {status.result.researched} topics researched · {status.result.failed} failed
          </Notice>
        )}
      </div>
      <div className="border-t border-ink-100 p-5">
        <div className="mb-3 flex items-center justify-between">
          <p className="text-sm font-semibold text-ink-800">Mock paper readiness</p>
          <Badge tone={readiness.is_ready ? 'green' : 'amber'}>{readiness.ready_questions}/{readiness.paper_size} questions</Badge>
        </div>
        <div className="grid gap-x-8 gap-y-2.5 sm:grid-cols-2">
          {readiness.chapters.map((c) => (
            <div key={c.chapter_id}>
              <div className="flex justify-between text-xs"><span className="truncate text-ink-600">{c.chapter_name}</span>
                <span className="num text-ink-500">{c.available} / {c.needed} needed</span></div>
              <ProgressBar className="mt-1 h-1.5" value={c.needed ? (100 * Math.min(c.available, c.needed * 3)) / (c.needed * 3) : 100} />
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs text-ink-500">Bars fill at 3× the questions needed per paper, so students get fresh papers on repeat attempts.</p>
      </div>
    </Card>
  )
}

// --------------------------------------------------------------------------- syllabus editor
function SyllabusEditor({ course, onSaved }) {
  const toast = useToast()
  const { data, loading } = useAsync(() => api.syllabus(course.id), [course.id])
  const [text, setText] = useState('')
  const [mode, setMode] = useState('merge')
  const [busy, setBusy] = useState(false)
  const [confirm, setConfirm] = useState(false)
  useEffect(() => { if (data) setText(data.text) }, [data])

  const lines = text.split('\n').filter((l) => l.trim())
  const topics = lines.filter((l) => /^\s*([-*•–·]|\d+\.\d+)\s/.test(l)).length
  const chapters = lines.length - topics

  const save = async () => {
    setBusy(true)
    try {
      const r = await api.importSyllabus(course.id, text, mode)
      toast.success(`Syllabus saved: ${r.chapters_created} new chapters, ${r.topics_created} new topics, ${r.topics_updated} updated.`)
      onSaved()
    } catch (err) {
      toast.error(err.message)
    } finally {
      setBusy(false)
      setConfirm(false)
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <Card className="overflow-hidden">
        <CardHeader icon={FileText} title="Syllabus outline" subtitle={`${chapters} chapters · ${topics} topics`} />
        {loading ? <div className="p-5"><Skeleton className="h-96" /></div> : (
          <textarea value={text} onChange={(e) => setText(e.target.value)} spellCheck={false}
            className="block h-[520px] w-full resize-y border-0 bg-ink-50/50 p-5 font-mono text-[13px] leading-6 text-ink-800 focus:ring-0"
            placeholder={'Computer Networks [6]\n- OSI model: layers, functions, PDUs\n- IP addressing: IPv4, IPv6, subnetting'} />
        )}
        <div className="flex flex-wrap items-center gap-3 border-t border-ink-100 p-4">
          <div className="flex rounded-xl bg-ink-100 p-1 text-sm">
            {[['merge', 'Add & update'], ['replace', 'Replace exactly']].map(([v, l]) => (
              <button key={v} onClick={() => setMode(v)}
                className={cx('rounded-lg px-3 py-1.5 font-semibold', mode === v ? 'bg-white shadow-sm text-ink-900' : 'text-ink-500')}>{l}</button>
            ))}
          </div>
          <Button className="ml-auto" onClick={() => (mode === 'replace' ? setConfirm(true) : save())} loading={busy}>Save syllabus</Button>
        </div>
      </Card>
      <div className="space-y-4">
        <Card className="p-5 text-sm leading-relaxed text-ink-600">
          <p className="mb-2 font-semibold text-ink-900">How to write it</p>
          <ul className="space-y-2">
            <li><b>Paper</b> (optional): a line starting with <code className="rounded bg-ink-100 px-1">Paper I</code> or <code className="rounded bg-ink-100 px-1">Part II</code>. Chapters below it belong to that paper, and students can take a mock test of each paper.</li>
            <li><b>Chapter</b>: any plain line. Add <code className="rounded bg-ink-100 px-1">[6]</code> at the end for its number of questions in the mock paper.</li>
            <li><b>Topic</b>: starts with <code className="rounded bg-ink-100 px-1">-</code>, <code className="rounded bg-ink-100 px-1">•</code> or <code className="rounded bg-ink-100 px-1">1.1</code>.</li>
            <li>Text after <code className="rounded bg-ink-100 px-1">:</code> is the topic&apos;s syllabus detail. It steers web research and questions.</li>
            <li>Paste the official notice and lightly tidy it. Numbering like “1.” or “Unit 2:” is understood.</li>
          </ul>
        </Card>
        <Notice tone="info" title="Your content is safe">Existing topics keep their PDFs, questions and student history. “Replace exactly” removes only the chapters and topics you deleted from the outline.</Notice>
      </div>
      <ConfirmModal open={confirm} title="Replace the syllabus?" confirmLabel="Replace" loading={busy} onConfirm={save} onClose={() => setConfirm(false)}
        message="Chapters and topics missing from the outline will be deleted, together with their questions, PDFs and student history." />
    </div>
  )
}

// --------------------------------------------------------------------------- structure
function EditModal({ state, onClose }) {
  const [values, setValues] = useState(state.values)
  const [busy, setBusy] = useState(false)
  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    try { await state.save(values); onClose() } catch { /* toast shown */ } finally { setBusy(false) }
  }
  return (
    <Modal open onClose={onClose} title={state.title}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button type="submit" form="edit-form" loading={busy}>Save</Button></>}>
      <form id="edit-form" onSubmit={submit} className="space-y-4">
        <Field label="Name"><Input required autoFocus value={values.name} onChange={(e) => setValues({ ...values, name: e.target.value })} /></Field>
        {'paper' in values && (
          <Field label="Paper" hint="Leave empty for single-paper courses, e.g. Paper I: Information Technology I.">
            <Input value={values.paper || ''} onChange={(e) => setValues({ ...values, paper: e.target.value })} />
          </Field>
        )}
        {'weight' in values && (
          <Field label="Questions in mock paper" hint="0 = share the remaining questions evenly.">
            <Input type="number" min={0} max={200} value={values.weight} onChange={(e) => setValues({ ...values, weight: Number(e.target.value) })} />
          </Field>
        )}
        {'description' in values && (
          <Field label="Syllabus detail" hint="What this topic covers. Guides research and question writing.">
            <Textarea value={values.description} onChange={(e) => setValues({ ...values, description: e.target.value })} />
          </Field>
        )}
      </form>
    </Modal>
  )
}

function Structure({ course, act }) {
  const [edit, setEdit] = useState(null)
  const [confirm, setConfirm] = useState(null)
  const move = (i, dir) => {
    const a = course.chapters[i]
    const b = course.chapters[i + dir]
    if (!b) return
    const bo = b.order === a.order ? a.order + dir : b.order
    act(async () => { await api.updateChapter(a.id, { order: Math.max(0, bo) }); await api.updateChapter(b.id, { order: Math.max(0, a.order) }) }).catch(() => {})
  }
  return (
    <div className="space-y-3">
      {groupByPaper(course.chapters).map((group) => (
        <div key={group.paper || 'all'} className="space-y-3">
          {group.paper && (
            <p className="flex items-center gap-2 pt-2 text-sm font-semibold text-ink-800">
              <span className="rounded-md bg-ink-900 px-2 py-0.5 text-xs text-white">{paperShort(group.paper)}</span>
              {group.paper} · {group.chapters.reduce((n, c) => n + (c.weight || 0), 0)} MCQs
            </p>
          )}
      {group.chapters.map((ch) => { const i = course.chapters.indexOf(ch); return (
        <Card key={ch.id} className="overflow-hidden">
          <div className="flex items-center gap-1 bg-ink-50/70 px-5 py-3">
            <span className="num mr-2 grid h-8 w-8 place-items-center rounded-lg bg-white text-sm font-bold text-ink-700 ring-1 ring-ink-200">{i + 1}</span>
            <div className="min-w-0 flex-1">
              <p className="truncate font-semibold text-ink-900">{ch.name}</p>
              <p className="text-xs text-ink-500">{ch.topics.length} topics · {ch.weight ? `${ch.weight} questions in paper` : 'auto weight'}</p>
            </div>
            <Button variant="ghost" size="xs" onClick={() => move(i, -1)} disabled={i === 0} aria-label="Move up"><ArrowUp className="h-4 w-4" /></Button>
            <Button variant="ghost" size="xs" onClick={() => move(i, 1)} disabled={i === course.chapters.length - 1} aria-label="Move down"><ArrowDown className="h-4 w-4" /></Button>
            <Button variant="ghost" size="xs" aria-label="Edit chapter" onClick={() => setEdit({ title: 'Edit chapter', values: { name: ch.name, weight: ch.weight, paper: ch.paper || '' },
              save: (v) => act(() => api.updateChapter(ch.id, v), 'Chapter saved') })}><Pencil className="h-4 w-4" /></Button>
            <Button variant="ghost" size="xs" aria-label="Delete chapter" onClick={() => setConfirm({ title: 'Delete chapter?',
              message: `"${ch.name}" and its ${ch.topics.length} topics, with their questions, PDFs and student history, will be permanently deleted.`,
              run: () => act(() => api.deleteChapter(ch.id), 'Chapter deleted') })}><Trash2 className="h-4 w-4 text-rose-500" /></Button>
          </div>
          <ul className="divide-y divide-ink-100">
            {ch.topics.map((t) => (
              <li key={t.id}>
                <Link to={`/admin/topics/${t.id}`} className="group flex items-center gap-3 px-5 py-2.5 hover:bg-brand-50/40">
                  <div className="min-w-0 flex-1 pl-0 sm:pl-10">
                    <p className="truncate text-sm font-medium text-ink-800 group-hover:text-brand-700">{t.name}</p>
                    {t.description && <p className="truncate text-xs text-ink-500">{t.description}</p>}
                  </div>
                  {t.has_content ? <Badge tone="green"><Globe className="h-3 w-3" /> Content</Badge> : <Badge>No content</Badge>}
                  <Badge tone={t.question_count ? 'blue' : 'slate'}>{t.question_count} Qs</Badge>
                  <ChevronRight className="h-4 w-4 text-ink-300" />
                </Link>
              </li>
            ))}
            <li className="px-5 py-2.5 sm:pl-[60px]">
              <button className="flex items-center gap-1 text-sm font-semibold text-brand-600 hover:underline"
                onClick={() => setEdit({ title: `New topic in “${ch.name}”`, values: { name: '', description: '' },
                  save: (v) => act(() => api.createTopic({ chapter_id: ch.id, name: v.name, description: v.description || null }), 'Topic added') })}>
                <Plus className="h-4 w-4" /> Add topic
              </button>
            </li>
          </ul>
        </Card>
      ) })}
        </div>
      ))}
      <Button variant="secondary" onClick={() => setEdit({ title: 'New chapter', values: { name: '', weight: 0, paper: '' },
        save: (v) => act(() => api.createChapter({ course_id: course.id, ...v, paper: v.paper || null }), 'Chapter added') })}><Plus className="h-4 w-4" /> Add chapter</Button>
      {edit && <EditModal key={edit.title} state={edit} onClose={() => setEdit(null)} />}
      <ConfirmModal open={Boolean(confirm)} title={confirm?.title} message={confirm?.message}
        onConfirm={async () => { try { await confirm.run() } catch { /* toast */ } setConfirm(null) }} onClose={() => setConfirm(null)} />
    </div>
  )
}

// --------------------------------------------------------------------------- exam pattern
function ExamPattern({ course, act }) {
  const [f, setF] = useState(() => ({
    name: course.name, description: course.description || '', exam_name: course.exam_name || '',
    exam_question_count: course.exam_question_count, exam_duration_minutes: course.exam_duration_minutes,
    negative_marking: course.negative_marking, pass_percent: course.pass_percent, exam_instructions: course.exam_instructions || '',
    marks_per_question: course.marks_per_question ?? 1, pass_rule: course.pass_rule || 'per_paper',
  }))
  const [busy, setBusy] = useState(false)
  const set = (k, num) => (e) => setF({ ...f, [k]: num ? Number(e.target.value) : e.target.value })
  const weighted = course.chapters.reduce((n, c) => n + (c.weight || 0), 0)
  const save = async (e) => {
    e.preventDefault()
    setBusy(true)
    try {
      await act(() => api.updateCourse(course.id, { ...f, exam_name: f.exam_name || null, description: f.description || null, exam_instructions: f.exam_instructions || null }), 'Exam pattern saved')
    } catch { /* toast */ } finally { setBusy(false) }
  }
  return (
    <form onSubmit={save} className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <Card className="space-y-5 p-6">
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Course name"><Input required value={f.name} onChange={set('name')} /></Field>
          <Field label="Exam name" hint="Shown to students; also steers question style."><Input value={f.exam_name} onChange={set('exam_name')} /></Field>
        </div>
        <Field label="Description"><Textarea value={f.description} onChange={set('description')} /></Field>
        <div className="grid gap-5 sm:grid-cols-4">
          <Field label="Questions"><Input type="number" min={5} max={200} value={f.exam_question_count} onChange={set('exam_question_count', true)} /></Field>
          <Field label="Minutes"><Input type="number" min={5} max={300} value={f.exam_duration_minutes} onChange={set('exam_duration_minutes', true)} /></Field>
          <Field label="Negative / wrong" hint="0.2 = 20%"><Input type="number" min={0} max={1} step={0.05} value={f.negative_marking} onChange={set('negative_marking', true)} /></Field>
          <Field label="Pass mark %"><Input type="number" min={0} max={100} value={f.pass_percent} onChange={set('pass_percent', true)} /></Field>
        </div>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Marks per question"><Input type="number" min={0.25} max={10} step={0.25} value={f.marks_per_question} onChange={set('marks_per_question', true)} /></Field>
          <Field label="Pass rule" hint="NRB: each paper must pass. Lok Sewa Paper I: combined score.">
            <select className="block w-full rounded-xl border-0 px-3.5 py-2.5 text-sm shadow-sm ring-1 ring-inset ring-ink-200" value={f.pass_rule} onChange={set('pass_rule')}>
              <option value="per_paper">Pass mark in each paper</option>
              <option value="overall">Pass mark on the combined total</option>
            </select>
          </Field>
        </div>
        <Field label="Instructions shown before the exam" hint="One instruction per line.">
          <Textarea className="min-h-[120px]" value={f.exam_instructions} onChange={set('exam_instructions')} />
        </Field>
        <div className="flex justify-end"><Button type="submit" loading={busy}>Save exam pattern</Button></div>
      </Card>
      <div className="space-y-4">
        <Notice tone={weighted > f.exam_question_count ? 'warn' : 'info'} icon={ClipboardList} title="Chapter weights">
          {weighted} of {f.exam_question_count} questions are assigned to chapters with an explicit weight; the rest are shared evenly.
          {weighted > f.exam_question_count && ' Weights add up to more than the paper size, so the paper will use the weights.'}
        </Notice>
        <Notice icon={Settings2}>Changes apply to new mock tests. Tests already started keep their original settings.</Notice>
      </div>
    </form>
  )
}

// --------------------------------------------------------------------------- question sources
const KINDS = [
  ['notes', 'Study notes', BookMarked, 'MCQs written in your notes'],
  ['ai', 'AI-written', Sparkles, 'Generated from your notes / web research'],
  ['past_paper', 'Past papers', History, 'Extracted from uploaded papers (OCR)'],
  ['online', 'Collected online', Globe, 'Old questions found on the web'],
]

function Sources({ course, papers }) {
  const toast = useToast()
  const poll = useTaskPoller()
  const { data, reload } = useAsync(() => api.questionSources(course.id), [course.id])
  const [file, setFile] = useState(null)
  const [label, setLabel] = useState('')
  const [paper, setPaper] = useState('')
  const [uploading, setUploading] = useState(null)
  const [collecting, setCollecting] = useState(null)

  const upload = async (e) => {
    e.preventDefault()
    if (!file) return
    setUploading('Uploading…')
    try {
      const { task_id: id } = await api.uploadPastPaper(course.id, file, label, paper)
      setUploading('Reading the paper (OCR if scanned) and extracting MCQs…')
      const r = await poll(id, { interval: 3000 })
      toast.success(`${label}: ${r.added} new MCQs added${r.ocr ? ' (OCR)' : ''}. ${r.duplicates} duplicates and ${r.off_syllabus} off-syllabus skipped.`)
      setFile(null)
      setLabel('')
      reload({ silent: true })
    } catch (err) {
      toast.error(err.message)
    } finally {
      setUploading(null)
    }
  }

  const collect = async () => {
    setCollecting({ current: 'Searching the web for old questions…' })
    try {
      const { task_id: id } = await api.collectOnline(course.id)
      const r = await poll(id, { interval: 3000, onUpdate: (s) => s.progress && setCollecting(s.progress) })
      toast.success(`Checked ${r.pages} pages: ${r.added} new MCQs added (${r.duplicates} duplicates skipped).`)
      reload({ silent: true })
    } catch (err) {
      toast.error(err.message)
    } finally {
      setCollecting(null)
    }
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {KINDS.map(([key, title, Icon, hint]) => (
          <Card key={key} className="p-5">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-ink-500">{title}</p>
              <Icon className="h-[18px] w-[18px] text-brand-600" />
            </div>
            <p className="num mt-2 text-2xl font-bold text-ink-900">{data?.by_kind?.[key] ?? 0}</p>
            <p className="mt-1 text-xs text-ink-500">{hint}</p>
          </Card>
        ))}
      </div>

      <PastPapers course={course} papers={papers} onChange={() => reload({ silent: true })} />

      <Notice icon={Sparkles} title="How students get fresh questions">
        Practice and mock tests serve questions a student hasn&apos;t seen first, then the ones seen longest ago. When a student runs low,
        the AI writes new questions on the spot from your notes; once the notes are exhausted it researches the web. Repeats stay rare.
      </Notice>
    </div>
  )
}

// --------------------------------------------------------------------------- page
export default function ManageCourse() {
  const { courseId } = useParams()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const toast = useToast()
  const tab = params.get('tab') || 'content'
  const { data, error, loading, reload } = useAsync(
    () => Promise.all([api.course(courseId), api.readiness(courseId)]).then(([course, readiness]) => ({ course, readiness })),
    [courseId],
  )
  const [confirmDelete, setConfirmDelete] = useState(false)

  const act = async (fn, ok) => {
    try {
      await fn()
      if (ok) toast.success(ok)
      await reload({ silent: true })
    } catch (err) {
      toast.error(err.message)
      throw err
    }
  }

  if (loading && !data) return <div className="space-y-4"><Skeleton className="h-16" /><Skeleton className="h-96" /></div>
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!data) return null
  const { course, readiness } = data
  const topicCount = course.chapters.reduce((n, c) => n + c.topics.length, 0)
  const questionCount = course.chapters.reduce((n, c) => n + c.topics.reduce((m, t) => m + t.question_count, 0), 0)

  return (
    <>
      <PageHeader
        breadcrumb={<Link to="/admin/courses" className="hover:text-ink-800">Courses & content</Link>}
        title={course.name}
        subtitle={`${course.chapters.length} chapters · ${topicCount} topics · ${questionCount} questions`}
        actions={<>
          <Badge tone={course.is_published ? 'green' : 'amber'} className="self-center px-3 py-1">{course.is_published ? 'Published' : 'Draft'}</Badge>
          <Link to={`/courses/${course.id}`}><Button variant="secondary"><Eye className="h-4 w-4" /> Student view</Button></Link>
          <Button variant={course.is_published ? 'secondary' : 'primary'}
            onClick={() => act(() => api.updateCourse(course.id, { is_published: !course.is_published }), course.is_published ? 'Course hidden from students' : 'Course published').catch(() => {})}>
            {course.is_published ? 'Unpublish' : 'Publish'}
          </Button>
          <Button variant="ghost" aria-label="Delete course" onClick={() => setConfirmDelete(true)}><Trash2 className="h-4 w-4 text-rose-500" /></Button>
        </>}
      />

      <Tabs value={tab} onChange={(t) => setParams({ tab: t })} tabs={[
        { value: 'content', label: 'Question bank', icon: Sparkles },
        { value: 'syllabus', label: 'Syllabus', icon: FileText },
        { value: 'structure', label: 'Chapters & topics', icon: Layers3 },
        { value: 'sources', label: 'Sources & past papers', icon: History },
        { value: 'pattern', label: 'Exam pattern', icon: ListChecks },
      ]} />

      {tab === 'content' && <BankBuilder course={course} readiness={readiness} onDone={() => reload({ silent: true })} />}
      {tab === 'syllabus' && <SyllabusEditor course={course} onSaved={() => reload({ silent: true })} />}
      {tab === 'structure' && <Structure course={course} act={act} />}
      {tab === 'pattern' && <ExamPattern key={course.id} course={course} act={act} />}
      {tab === 'sources' && <Sources course={course} papers={papersOf(course.chapters)} />}

      <ConfirmModal open={confirmDelete} title="Delete this course?"
        message={`"${course.name}" with all chapters, topics, questions, PDFs, mock tests and student results will be permanently deleted. This cannot be undone.`}
        onClose={() => setConfirmDelete(false)}
        onConfirm={async () => {
          try { await api.deleteCourse(course.id); toast.success('Course deleted'); navigate('/admin/courses') } catch (err) { toast.error(err.message); setConfirmDelete(false) }
        }} />
    </>
  )
}
