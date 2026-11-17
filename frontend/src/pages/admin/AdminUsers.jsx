import { useMemo, useState } from 'react'
import { Search, ShieldCheck, Users } from 'lucide-react'
import { api } from '../../api/client'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useAsync } from '../../hooks/useAsync'
import { Badge, Button, Card, ConfirmModal, ErrorBox, Input, PageHeader, Skeleton, Stat } from '../../components/ui'
import { formatDate } from '../../utils/format'

export default function AdminUsers() {
  const { user: me } = useAuth()
  const toast = useToast()
  const { data, error, loading, reload, setData } = useAsync(() => api.users(), [])
  const [q, setQ] = useState('')
  const [confirm, setConfirm] = useState(null)

  const rows = useMemo(() => {
    const n = q.trim().toLowerCase()
    return (data || []).filter((u) => !n || u.email.includes(n) || (u.full_name || '').toLowerCase().includes(n))
  }, [data, q])

  const update = async (u, patch) => {
    try {
      const updated = await api.updateUser(u.id, patch)
      setData((list) => list.map((x) => (x.id === u.id ? updated : x)))
      toast.success('Account updated')
    } catch (err) {
      toast.error(err.message)
    }
    setConfirm(null)
  }

  const admins = (data || []).filter((u) => u.is_admin).length
  const active = (data || []).filter((u) => u.is_active).length

  return (
    <>
      <PageHeader eyebrow="Administration" title="Students & staff" subtitle="Everyone with an account on your platform." />
      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <Stat icon={Users} label="Accounts" value={data?.length ?? '—'} />
        <Stat icon={Users} label="Active" value={data ? active : '—'} tone="green" />
        <Stat icon={ShieldCheck} label="Administrators" value={data ? admins : '—'} tone="violet" />
      </div>
      <ErrorBox error={error} onRetry={reload} />
      <Card>
        <div className="border-b border-ink-100 p-4">
          <div className="relative max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-ink-400" />
            <div className="[&_input]:pl-9"><Input placeholder="Search by name or e-mail" value={q} onChange={(e) => setQ(e.target.value)} /></div>
          </div>
        </div>
        {loading && !data ? <div className="p-5"><Skeleton className="h-40" /></div> : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-ink-500">
                <tr><th className="px-5 py-3">Name</th><th className="px-5 py-3">Joined</th><th className="px-5 py-3">Role</th><th className="px-5 py-3">Status</th><th className="px-5 py-3 text-right">Actions</th></tr>
              </thead>
              <tbody className="divide-y divide-ink-100">
                {rows.map((u) => {
                  const self = u.id === me.id
                  return (
                    <tr key={u.id} className="hover:bg-ink-50/60">
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-3">
                          <span className="grid h-8 w-8 place-items-center rounded-full bg-brand-100 text-xs font-bold text-brand-700">{(u.full_name || u.email)[0].toUpperCase()}</span>
                          <div><p className="font-semibold text-ink-900">{u.full_name || '—'} {self && <span className="text-xs font-normal text-ink-400">(you)</span>}</p><p className="text-xs text-ink-500">{u.email}</p></div>
                        </div>
                      </td>
                      <td className="px-5 py-3 text-ink-500">{formatDate(u.created_at)}</td>
                      <td className="px-5 py-3"><Badge tone={u.is_admin ? 'violet' : 'slate'}>{u.is_admin ? 'Admin' : 'Student'}</Badge></td>
                      <td className="px-5 py-3"><Badge tone={u.is_active ? 'green' : 'red'}>{u.is_active ? 'Active' : 'Disabled'}</Badge></td>
                      <td className="px-5 py-3">
                        <div className="flex justify-end gap-2">
                          <Button size="xs" variant="secondary" disabled={self}
                            onClick={() => setConfirm({ title: u.is_admin ? 'Remove admin access?' : 'Make administrator?',
                              message: u.is_admin ? `${u.email} will become a student.` : `${u.email} will be able to manage courses, content, users and settings.`,
                              run: () => update(u, { is_admin: !u.is_admin }), label: u.is_admin ? 'Remove admin' : 'Make admin', variant: 'primary' })}>
                            {u.is_admin ? 'Remove admin' : 'Make admin'}
                          </Button>
                          <Button size="xs" variant={u.is_active ? 'ghost' : 'soft'} disabled={self}
                            onClick={() => (u.is_active
                              ? setConfirm({ title: 'Disable account?', message: `${u.email} won't be able to sign in until re-enabled. Their results are kept.`,
                                run: () => update(u, { is_active: false }), label: 'Disable', variant: 'danger' })
                              : update(u, { is_active: true }))}>
                            {u.is_active ? 'Disable' : 'Enable'}
                          </Button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <ConfirmModal open={Boolean(confirm)} title={confirm?.title} message={confirm?.message} confirmLabel={confirm?.label}
        variant={confirm?.variant} onConfirm={() => confirm.run()} onClose={() => setConfirm(null)} />
    </>
  )
}
