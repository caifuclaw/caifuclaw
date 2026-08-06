/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { SizeType } from 'antd/es/config-provider/SizeContext'

interface AppState {
  darkMode: boolean
  componentSize: SizeType
  sidebarCollapsed: boolean
  toggleDark: () => void
  setDark: (value: boolean) => void
  setSidebarCollapsed: (value: boolean) => void
  setComponentSize: (size: SizeType) => void
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      darkMode: false,
      componentSize: 'middle',
      sidebarCollapsed: false,
      toggleDark: () => set((s) => ({ darkMode: !s.darkMode })),
      setDark: (value) => set({ darkMode: value }),
      setSidebarCollapsed: (value) => set({ sidebarCollapsed: value }),
      setComponentSize: (size) => set({ componentSize: size })
    }),
    {
      name: 'caifuclaw:app',
      version: 2,
      partialize: (state) => ({
        componentSize: state.componentSize,
        sidebarCollapsed: state.sidebarCollapsed
      }),
      merge: (persistedState, currentState) => {
        const state = persistedState as Partial<Pick<AppState, 'componentSize' | 'sidebarCollapsed'>>
        return {
          ...currentState,
          componentSize: state.componentSize ?? currentState.componentSize,
          sidebarCollapsed: state.sidebarCollapsed ?? currentState.sidebarCollapsed
        }
      }
    }
  )
)
