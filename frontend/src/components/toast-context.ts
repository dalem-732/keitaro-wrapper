import { createContext, useContext } from 'react'

export type ToastKind = 'ok' | 'error' | 'info'

export const ToastContext = createContext<(text: string, kind?: ToastKind) => void>(() => {})

export const useToast = () => useContext(ToastContext)
