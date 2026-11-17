import { useState } from 'react'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { Badge, Button, Card, Field, Input, PageHeader } from '../components/ui'
import { formatDate } from '../utils/format'

export default function ProfilePage() {
  const { user, setUser } = useAuth()
  const toast = useToast()
  const [name, setName] = useState(user?.full_name || '')
  const [pw, setPw] = useState({ current: '', next: '', confirm: '' })
  const [busy, setBusy] = useState(null)

  const saveName = async (e) => {
    e.preventDefault()
    setBusy('name')
    try {
      setUser(await api.updateMe({ full_name: name }))
      toast.success('Profile updated')
    } catch (err) {
      toast.error(err.message)
    } finally {
      setBusy(null)
    }
  }

  const savePassword = async (e) => {
    e.preventDefault()
    if (pw.next !== pw.confirm) return toast.error('New passwords do not match')
    setBusy('pw')
    try {
      await api.updateMe({ current_password: pw.current, new_password: pw.next })
      setPw({ current: '', next: '', confirm: '' })
      toast.success('Password changed')
    } catch (err) {
      toast.error(err.message)
    } finally {
      setBusy(null)
    }
    return null
  }

  return (
    <div className="max-w-2xl">
      <PageHeader title="Profile" />
      <Card className="mb-6 p-5">
        <div className="mb-4 flex flex-wrap items-center gap-2 text-sm text-slate-500">
          <span>{user.email}</span>
          {user.is_admin && <Badge tone="violet">Administrator</Badge>}
          <span>· member since {formatDate(user.created_at)}</span>
        </div>
        <form onSubmit={saveName} className="flex items-end gap-3">
          <div className="flex-1">
            <Field label="Display name">
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
          </div>
          <Button type="submit" loading={busy === 'name'}>
            Save
          </Button>
        </form>
      </Card>
      <Card className="p-5">
        <h2 className="mb-4 font-semibold text-slate-900 dark:text-white">Change password</h2>
        <form onSubmit={savePassword} className="space-y-3">
          <Field label="Current password">
            <Input type="password" required value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} />
          </Field>
          <Field label="New password">
            <Input type="password" required minLength={8} value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} />
          </Field>
          <Field label="Confirm new password">
            <Input type="password" required value={pw.confirm} onChange={(e) => setPw({ ...pw, confirm: e.target.value })} />
          </Field>
          <Button type="submit" loading={busy === 'pw'}>
            Update password
          </Button>
        </form>
      </Card>
    </div>
  )
}
