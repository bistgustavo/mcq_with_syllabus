import { useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Eye, FileText, Globe, Pencil, RotateCcw, Search, Trash2, UploadCloud } from 'lucide-react'
import { api } from '../../api/client'
import { useToast } from '../../context/ToastContext'
import { useAsync, useInterval, useTaskPoller } from '../../hooks/useAsync'
import GenerationPanel from '../../components/GenerationPanel'
import {
  Badge,
  Button,
  Card,
  ConfirmModal,
  DifficultyBadge,
  ErrorBox,
  Field,
  Input,
  Modal,
  PageHeader,
  Select,
  Spinner,
  StatusBadge,
  Textarea,
  cx,
} from '../../components/ui'
import { DIFFICULTIES, LETTERS, formatBytes, sourceLabel, timeAgo } from '../../utils/format'

const PAGE = 10

// --------------------------------------------------------------------------- uploads
function DocumentsPanel({ topicId, status, onChange }) {
  const toast = useToast()
  const input = useRef(null)
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [confirm, setConfirm] = useState(null)

  const upload = async (files) => {
    const pdfs = [...files].filter((f) => f.name.toLowerCase().endsWith('.pdf'))
    if (!pdfs.length) return toast.error('Please choose PDF files')
    setUploading(true)
    for (const file of pdfs) {
      try {
        await api.upload(topicId, file)
        toast.success(`Uploaded ${file.name}. Ingestion started.`)
      } catch (err) {
        toast.error(`${file.name}: ${err.message}`)
      }
    }
    setUploading(false)
    onChange()
    return null
  }

  const docs = status?.documents || []
  const uploads = docs.filter((d) => d.source_type === 'upload')
  const isChapterDoc = (d) => !d.topic_id
  const web = docs.filter((d) => d.source_type === 'web_search')

  return (
    <Card className="p-5">
      <h2 className="font-semibold text-slate-900 dark:text-white">Syllabus notes</h2>
      <p className="mb-4 mt-1 text-xs text-slate-500">
        PDFs are split into chunks, embedded and stored in Qdrant. Questions are generated from these chunks.
        {status && ` ${status.chunk_count} chunk(s) indexed.`}
      </p>

      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          upload(e.dataTransfer.files)
        }}
        onClick={() => input.current?.click()}
        className={cx(
          'flex cursor-pointer flex-col items-center rounded-xl border-2 border-dashed px-4 py-8 text-center transition',
          dragging ? 'border-brand-500 bg-brand-50 dark:bg-brand-900/20' : 'border-slate-300 hover:border-brand-400 dark:border-slate-600',
        )}
      >
        <UploadCloud className="mb-2 h-8 w-8 text-slate-400" />
        <p className="text-sm font-medium">{uploading ? 'Uploading…' : 'Drop PDFs here or click to browse'}</p>
        <p className="text-xs text-slate-500">Text-based PDFs only (scanned images have no extractable text)</p>
        <input
          ref={input}
          type="file"
          accept="application/pdf,.pdf"
          multiple
          hidden
          onChange={(e) => {
            upload(e.target.files)
            e.target.value = ''
          }}
        />
      </div>

      {uploads.length > 0 && (
        <ul className="mt-4 divide-y divide-slate-100 dark:divide-slate-700">
          {uploads.map((d) => (
            <li key={d.id} className="flex items-center gap-3 py-2.5">
              <FileText className="h-4 w-4 shrink-0 text-slate-400" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{d.filename}</p>
                <p className="text-xs text-slate-500">
                  {formatBytes(d.file_size)}
                  {d.page_count ? ` · ${d.page_count} pages` : ''}
                  {d.chunk_count ? ` · ${d.chunk_count} chunks` : ''} · {timeAgo(d.created_at)}
                </p>
                {d.error && <p className="text-xs text-rose-600">{d.error}</p>}
              </div>
              {isChapterDoc(d) && <Badge tone="violet">Whole chapter</Badge>}
              <StatusBadge status={d.status} />
              {(d.status === 'failed' || d.status === 'empty') && (
                <Button
                  variant="ghost"
                  size="sm"
                  title="Retry ingestion"
                  onClick={() =>
                    api
                      .reingest(topicId, d.id)
                      .then(() => {
                        toast.info('Re-ingestion started')
                        onChange()
                      })
                      .catch((err) => toast.error(err.message))
                  }
                >
                  <RotateCcw className="h-4 w-4" />
                </Button>
              )}
              {!isChapterDoc(d) && (
                <Button variant="ghost" size="sm" title="Delete document" onClick={() => setConfirm(d)}>
                  <Trash2 className="h-4 w-4 text-rose-500" />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}

      {web.length > 0 && (
        <details className="mt-4 text-sm">
          <summary className="cursor-pointer text-slate-500">
            <Globe className="mr-1 inline h-4 w-4" /> {web.length} web source(s) used as fallback context
          </summary>
          <ul className="mt-2 space-y-1 pl-5">
            {web.map((d) => (
              <li key={d.id} className="truncate text-xs text-slate-500">
                {d.filename.replace(/^web:/, '')}
              </li>
            ))}
          </ul>
        </details>
      )}

      <ConfirmModal
        open={Boolean(confirm)}
        title="Delete document?"
        message={`"${confirm?.filename}" and its indexed chunks will be removed. Questions already generated from it are kept.`}
        onClose={() => setConfirm(null)}
        onConfirm={async () => {
          try {
            await api.deleteDocument(topicId, confirm.id)
            toast.success('Document deleted')
            onChange()
          } catch (err) {
            toast.error(err.message)
          }
          setConfirm(null)
        }}
      />
    </Card>
  )
}

// --------------------------------------------------------------------------- question bank
function QuestionBank({ topicId, refreshKey }) {
  const toast = useToast()
  const [offset, setOffset] = useState(0)
  const [difficulty, setDifficulty] = useState('')
  const [revealed, setRevealed] = useState(() => new Set())
  const { data, error, loading, reload } = useAsync(
    () => api.questions(topicId, { limit: PAGE, offset, difficulty: difficulty || undefined }),
    [topicId, offset, difficulty, refreshKey],
  )

  const toggle = (id) =>
    setRevealed((s) => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const remove = async (q) => {
    try {
      await api.deleteQuestion(topicId, q.id)
      toast.success('Question deleted')
      reload({ silent: true })
    } catch (err) {
      toast.error(err.message)
    }
  }

  return (
    <Card className="p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-semibold text-slate-900 dark:text-white">
          Question bank {data && <span className="text-sm font-normal text-slate-500">({data.total})</span>}
        </h2>
        <div className="w-40">
          <Select
            value={difficulty}
            onChange={(e) => {
              setDifficulty(e.target.value)
              setOffset(0)
            }}
          >
            <option value="">All difficulties</option>
            {DIFFICULTIES.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </Select>
        </div>
      </div>
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data ? (
        <Spinner />
      ) : data?.items.length === 0 ? (
        <p className="py-6 text-center text-sm text-slate-500">No questions yet. Use the generator to create some.</p>
      ) : (
        <ul className="space-y-3">
          {data?.items.map((q) => (
            <li key={q.id} className="rounded-xl border border-slate-200 p-4 dark:border-slate-700">
              <div className="flex items-start gap-3">
                <p className="flex-1 text-sm font-medium">{q.question_text}</p>
                <DifficultyBadge value={q.difficulty} />
                <Badge tone={sourceLabel(q.source, q.reference).tone} className="max-w-[16rem] truncate">{sourceLabel(q.source, q.reference).text}</Badge>
              </div>
              <ol className="mt-2 grid gap-1 text-sm sm:grid-cols-2">
                {q.options.map((opt, i) => (
                  <li
                    key={i}
                    className={cx(
                      'rounded-md px-2 py-1',
                      revealed.has(q.id) && i === q.correct_index
                        ? 'bg-emerald-50 font-medium text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300'
                        : 'text-slate-600 dark:text-slate-300',
                    )}
                  >
                    {LETTERS[i]}. {opt}
                  </li>
                ))}
              </ol>
              {revealed.has(q.id) && q.explanation && (
                <p className="mt-2 text-xs text-slate-500">
                  <span className="font-semibold">Why: </span>
                  {q.explanation}
                </p>
              )}
              <div className="mt-2 flex gap-2">
                <Button variant="ghost" size="sm" onClick={() => toggle(q.id)}>
                  <Eye className="h-3.5 w-3.5" /> {revealed.has(q.id) ? 'Hide answer' : 'Show answer'}
                </Button>
                <Button variant="ghost" size="sm" onClick={() => remove(q)}>
                  <Trash2 className="h-3.5 w-3.5 text-rose-500" /> Delete
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {data && data.total > PAGE && (
        <div className="mt-4 flex items-center justify-between text-sm text-slate-500">
          <Button variant="secondary" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
            Previous
          </Button>
          <span>
            {offset + 1}–{Math.min(offset + PAGE, data.total)} of {data.total}
          </span>
          <Button variant="secondary" size="sm" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>
            Next
          </Button>
        </div>
      )}
    </Card>
  )
}

// --------------------------------------------------------------------------- page
export default function ManageTopic() {
  const { topicId } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const topic = useAsync(() => api.topic(topicId), [topicId])
  const status = useAsync(() => api.topicStatus(topicId), [topicId])
  const [bankKey, setBankKey] = useState(0)
  const [researching, setResearching] = useState(false)
  const pollTask = useTaskPoller()
  const [editing, setEditing] = useState(null)
  const [confirmDelete, setConfirmDelete] = useState(false)

  // While any document is queued/processing, refresh its status every 3 s.
  useInterval(
    () => {
      status.reload({ silent: true })
      topic.reload({ silent: true })
    },
    3000,
    Boolean(status.data?.processing),
  )

  if (topic.loading && !topic.data) return <Spinner />
  if (topic.error) return <ErrorBox error={topic.error} onRetry={topic.reload} />
  const t = topic.data
  if (!t) return null

  const research = async () => {
    setResearching(true)
    try {
      const { task_id: id } = await api.research(topicId)
      const result = await pollTask(id)
      toast.success(`Found ${result.sources} source(s) and stored ${result.stored} passages for this topic.`)
      status.reload({ silent: true })
      topic.reload({ silent: true })
    } catch (err) {
      toast.error(err.message)
    } finally {
      setResearching(false)
    }
  }

  const save = async (e) => {
    e.preventDefault()
    try {
      await api.updateTopic(t.id, { name: editing.name, description: editing.description || null })
      toast.success('Topic saved')
      setEditing(null)
      topic.reload({ silent: true })
    } catch (err) {
      toast.error(err.message)
    }
  }

  return (
    <>
      <PageHeader
        breadcrumb={
          <>
            <Link to="/admin/courses" className="hover:underline">
              Courses
            </Link>{' '}
            /{' '}
            <Link to={`/admin/courses/${t.course_id}?tab=structure`} className="hover:underline">
              {t.course_name}
            </Link>{' '}
            / {t.chapter_name}
          </>
        }
        title={t.name}
        subtitle={t.description}
        actions={
          <>
            <Button variant="soft" onClick={research} loading={researching}>
              <Search className="h-4 w-4" /> {researching ? 'Researching…' : 'Research on the web'}
            </Button>
            <Link to={`/topics/${t.id}`}>
              <Button variant="secondary">
                <Eye className="h-4 w-4" /> Student view
              </Button>
            </Link>
            <Button variant="secondary" onClick={() => setEditing({ name: t.name, description: t.description || '' })}>
              <Pencil className="h-4 w-4" /> Edit
            </Button>
            <Button variant="danger" title="Delete topic" onClick={() => setConfirmDelete(true)}>
              <Trash2 className="h-4 w-4" />
            </Button>
          </>
        }
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <ErrorBox error={status.error} onRetry={status.reload} />
          <DocumentsPanel
            topicId={t.id}
            status={status.data}
            onChange={() => {
              status.reload({ silent: true })
              topic.reload({ silent: true })
            }}
          />
          <QuestionBank topicId={t.id} refreshKey={bankKey} />
        </div>
        <div>
          <GenerationPanel
            topicId={t.id}
            hasContent={t.has_content}
            onGenerated={() => {
              setBankKey((k) => k + 1)
              topic.reload({ silent: true })
              status.reload({ silent: true })
            }}
          />
        </div>
      </div>

      <Modal
        open={Boolean(editing)}
        onClose={() => setEditing(null)}
        title="Edit topic"
        footer={
          <>
            <Button variant="secondary" onClick={() => setEditing(null)}>
              Cancel
            </Button>
            <Button type="submit" form="topic-form">
              Save
            </Button>
          </>
        }
      >
        {editing && (
          <form id="topic-form" onSubmit={save} className="space-y-4">
            <Field label="Name">
              <Input required value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} />
            </Field>
            <Field label="Syllabus detail" hint="What this topic covers. Shown to students, and used to guide web research and questions.">
              <Textarea value={editing.description} onChange={(e) => setEditing({ ...editing, description: e.target.value })} />
            </Field>
          </form>
        )}
      </Modal>

      <ConfirmModal
        open={confirmDelete}
        title="Delete topic?"
        message={`"${t.name}" with its notes, ${t.question_count} question(s) and all quiz history will be permanently deleted.`}
        onClose={() => setConfirmDelete(false)}
        onConfirm={async () => {
          try {
            await api.deleteTopic(t.id)
            toast.success('Topic deleted')
            navigate(`/admin/courses/${t.course_id}`)
          } catch (err) {
            toast.error(err.message)
            setConfirmDelete(false)
          }
        }}
      />
    </>
  )
}
