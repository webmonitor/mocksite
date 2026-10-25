import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { AdminApp } from './App'
import './styles.css'

const root = document.getElementById('admin-root')
if (!root) throw new Error('Missing #admin-root')
createRoot(root).render(
  <StrictMode>
    <AdminApp />
  </StrictMode>,
)
