import { useCallback, useState, type ReactNode } from 'react'
import { ToastContext, type ToastKind as Kind } from './toast-context'

interface ToastItem {
  id: number
  kind: Kind
  text: string
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const push = useCallback((text: string, kind: Kind = 'info') => {
    const id = Date.now() + Math.random()
    setItems((list) => [...list, { id, kind, text }])
    setTimeout(() => setItems((list) => list.filter((t) => t.id !== id)), kind === 'error' ? 7000 : 3500)
  }, [])
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toasts">
        {items.map((t) => (
          <div key={t.id} className={`toast toast-${t.kind}`} onClick={() => setItems((l) => l.filter((x) => x.id !== t.id))}>
            {t.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
