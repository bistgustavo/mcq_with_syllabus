import { Link } from 'react-router-dom'
import { Button, EmptyState } from '../components/ui'

export default function NotFound() {
  return (
    <EmptyState
      title="Page not found"
      action={
        <Link to="/">
          <Button>Go to dashboard</Button>
        </Link>
      }
    >
      The page you are looking for does not exist.
    </EmptyState>
  )
}
