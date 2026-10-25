import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

// Admin UI (authentication, state overview, editing, scenarios) lands in
// stage 3. This entry exists so the toolchain and build are verifiable now.
function AdminApp() {
  return (
    <main>
      <h1>mocksite admin</h1>
      <p>The admin interface is not implemented yet.</p>
    </main>
  )
}

const root = document.getElementById('admin-root')
if (!root) throw new Error('Missing #admin-root')
createRoot(root).render(
  <StrictMode>
    <AdminApp />
  </StrictMode>,
)
