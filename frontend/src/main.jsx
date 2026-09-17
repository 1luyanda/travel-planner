import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { AuthProvider } from './auth/AuthProvider'
import { RouteProvider } from './utils/routes.jsx'
import './styles.css'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AuthProvider>
      <RouteProvider>
        <App />
      </RouteProvider>
    </AuthProvider>
  </StrictMode>,
)

