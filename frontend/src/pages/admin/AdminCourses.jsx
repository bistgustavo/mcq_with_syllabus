import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, Library, Plus } from 'lucide-react'
import { api } from '../../api/client'
import { useToast } from '../../context/ToastContext'
import { useAsync } from '../../hooks/useAsync'
import { Badge, Button, Card, EmptyState, ErrorBox, Field, Input, Modal, PageHeader, Skeleton, Textarea } from '../../components/ui'

export default function AdminCourses() {
  const toast = useToast()
  const navigate = useNavigate()
  const { data, error, loading, reload } = useAsync(() => api.courses(), [])
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ name: '', exam_name: '', description: '' })
  const [busy, setBusy] = useState(false)

  const create = async (e) => {
    e.preventDefault()
    setBusy(true)
    try {
      const c = await api.createCourse({ name: form.name, exam_name: form.exam_name || null, description: form.description || null, is_published: false })
      toast.success('Course created. Now paste its syllabus.')
      navigate(`/admin/courses/${c.id}?tab=syllabus`)
    } catch (err) {
      toast.error(err.message)
      setBusy(false)
    }
  }

  return (
    <>
      <PageHeader eyebrow="Administration" title="Courses & content" subtitle="Each course has a syllabus, an exam pattern and a question bank."
        actions={<Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> New course</Button>} />
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data ? <Skeleton className="h-48" /> : (data || []).length === 0 ? (
        <EmptyState icon={Library} title="No courses yet" action={<Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> Create your first course</Button>}>
          Create a course, paste the official syllabus, then let the platform research and write the questions.
        </EmptyState>
      ) : (
        <Card className="divide-y divide-ink-100">
          {data.map((c) => (
            <Link key={c.id} to={`/admin/courses/${c.id}`} className="group flex items-center gap-4 px-5 py-4 hover:bg-ink-50">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-600"><Library className="h-5 w-5" /></span>
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold text-ink-900">{c.name}</p>
                <p className="text-sm text-ink-500">{c.chapter_count} chapters · {c.topic_count} topics · {c.question_count} questions</p>
              </div>
              <Badge tone={c.is_published ? 'green' : 'amber'}>{c.is_published ? 'Published' : 'Draft'}</Badge>
              <ArrowRight className="h-4 w-4 text-ink-300 group-hover:text-brand-600" />
            </Link>
          ))}
        </Card>
      )}

      <Modal open={open} onClose={() => setOpen(false)} title="New course"
        footer={<><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button type="submit" form="new-course" loading={busy}>Create course</Button></>}>
        <form id="new-course" onSubmit={create} className="space-y-4">
          <Field label="Course name"><Input required autoFocus placeholder="e.g. NRB Assistant Director (IT)" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <Field label="Exam name" hint="Used to make questions match this exam's style.">
            <Input placeholder="e.g. Nepal Rastra Bank – IT Officer" value={form.exam_name} onChange={(e) => setForm({ ...form, exam_name: e.target.value })} />
          </Field>
          <Field label="Short description"><Textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
          <p className="text-xs text-ink-500">The course starts as a draft. Publish it when the syllabus and questions are ready.</p>
        </form>
      </Modal>
    </>
  )
}
