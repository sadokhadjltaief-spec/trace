'use client'

import { useState } from 'react'
import { ChevronRight, FolderOpen, Gamepad2, House, LogOut, MessageCircle, Settings, SlidersHorizontal, UserRound, X } from 'lucide-react'
import { WaslaLogo } from '@/components/wasla-logo'
import { LanguageSwitcher } from '@/components/language-switcher'
import { cn } from '@/lib/utils'
import { ThemeToggle } from '@/components/theme-toggle'
import { TOOLS, type ToolId } from './tools'
import type { DashboardCopy } from './dashboard-copy'

export type NavId = 'home' | 'tutor' | 'content' | 'preferences'

type Props = {
  copy: DashboardCopy
  active: NavId
  onNavigate: (id: NavId) => void
  onTool: (id: ToolId) => void
  activeTool: ToolId | null
  showGames: boolean
  gamesActive: boolean
  onOpenGames: () => void
  name: string
  email: string
  signOutLabel: string
  onSignOut: () => void
  onOpenProfile: () => void
  onOpenSettings: () => void
  open: boolean
  onClose: () => void
}

export function Sidebar({ copy, active, onNavigate, onTool, activeTool, showGames, gamesActive, onOpenGames, name, email, signOutLabel, onSignOut, onOpenProfile, onOpenSettings, open, onClose }: Props) {
  const [accountMenuOpen, setAccountMenuOpen] = useState(false)
  const nav: { id: NavId; label: string; icon: typeof House }[] = [
    { id: 'home', label: copy.nav.home, icon: House },
    { id: 'tutor', label: copy.nav.tutor, icon: MessageCircle },
    { id: 'content', label: copy.nav.content, icon: FolderOpen },
    { id: 'preferences', label: copy.nav.preferences, icon: SlidersHorizontal },
  ]

  return (
    <>
      <div
        aria-hidden="true"
        onClick={onClose}
        className={cn('fixed inset-0 z-30 bg-ink/50 transition lg:hidden', open ? 'opacity-100' : 'pointer-events-none opacity-0')}
      />
      <aside
        className={cn(
          'fixed inset-y-0 start-0 z-40 flex w-72 flex-col bg-ink text-ink-foreground transition-transform lg:sticky lg:top-0 lg:h-dvh lg:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full rtl:translate-x-full lg:rtl:translate-x-0',
        )}
      >
        <div className="flex items-center justify-between px-5 pt-4">
          <WaslaLogo className="h-14 w-32" />
          <button
            type="button"
            onClick={onClose}
            aria-label={copy.closeMenu}
            className="flex size-9 items-center justify-center rounded-lg text-ink-muted hover:bg-ink-surface hover:text-ink-foreground lg:hidden"
          >
            <X className="size-5" aria-hidden="true" />
          </button>
        </div>

        <nav className="flex flex-1 flex-col gap-6 overflow-y-auto px-3 py-6">
          <ul className="flex flex-col gap-1">
            {nav.map((item) => {
              const isActive = item.id === active && activeTool === null && !gamesActive
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => { setAccountMenuOpen(false); onNavigate(item.id) }}
                    aria-current={isActive ? 'page' : undefined}
                    className={cn(
                      'flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition',
                      isActive ? 'bg-primary text-primary-foreground' : 'text-ink-muted hover:bg-ink-surface hover:text-ink-foreground',
                    )}
                  >
                    <item.icon className="size-5" aria-hidden="true" />
                    {item.label}
                  </button>
                </li>
              )
            })}
          </ul>

          <div className="flex flex-col gap-1">
            <p className="px-3 pb-1 text-xs font-semibold uppercase tracking-wider text-ink-muted">{copy.createLabel}</p>
            <ul className="flex flex-col gap-1">
              {TOOLS.map((tool) => {
                const isToolActive = tool.id === activeTool
                return (
                <li key={tool.id}>
                  <button
                    type="button"
                    onClick={() => { setAccountMenuOpen(false); onTool(tool.id) }}
                    aria-current={isToolActive ? 'page' : undefined}
                    className={cn('group flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition', isToolActive ? 'bg-primary text-primary-foreground' : 'text-ink-foreground/90 hover:bg-ink-surface')}
                  >
                    <tool.icon className={cn('size-5', isToolActive ? 'text-primary-foreground' : 'text-brand-cyan')} aria-hidden="true" />
                    <span className="flex-1 text-start">{copy.tools[tool.id].title}</span>
                    <ChevronRight className="size-4 text-ink-muted transition group-hover:text-ink-foreground rtl:rotate-180" aria-hidden="true" />
                  </button>
                </li>
                )
              })}
              {showGames ? (
                <li>
                  <button
                    type="button"
                    onClick={() => { setAccountMenuOpen(false); onOpenGames() }}
                    aria-current={gamesActive ? 'page' : undefined}
                    className={cn('group flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition', gamesActive ? 'bg-primary text-primary-foreground' : 'text-ink-foreground/90 hover:bg-ink-surface')}
                  >
                    <Gamepad2 className={cn('size-5', gamesActive ? 'text-primary-foreground' : 'text-brand-cyan')} aria-hidden="true" />
                    <span className="flex-1 text-start">{copy.tools.games.title}</span>
                    <ChevronRight className="size-4 text-ink-muted transition group-hover:text-ink-foreground rtl:rotate-180" aria-hidden="true" />
                  </button>
                </li>
              ) : null}
            </ul>
          </div>
        </nav>

        <div className="flex flex-col gap-3 border-t border-ink-border p-4">
          <div className="flex items-center gap-2">
            <LanguageSwitcher tone="dark" />
            <ThemeToggle labels={copy.theme} />
          </div>
          <div className="relative">
            <button
              type="button"
              onClick={() => setAccountMenuOpen((value) => !value)}
              aria-expanded={accountMenuOpen}
              aria-haspopup="menu"
              aria-controls="account-menu"
              className="flex w-full items-center gap-3 rounded-xl p-1.5 text-start transition hover:bg-ink-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
            >
              <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-[#65473f] text-sm font-bold text-white ring-2 ring-ink-border">
                {(name.trim()[0] || 'W').toUpperCase()}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-semibold">{name || copy.student}</span>
                <span className="block truncate text-xs text-ink-muted" dir="ltr">{email || copy.student}</span>
              </span>
              <ChevronRight className={cn('size-5 shrink-0 text-ink-muted transition-transform', accountMenuOpen && 'rotate-90')} aria-hidden="true" />
            </button>

            {accountMenuOpen && (
              <div id="account-menu" role="menu" aria-label="Account menu" className="fixed bottom-24 start-4 z-50 max-h-[min(78dvh,700px)] w-[min(420px,calc(100vw-2rem))] overflow-y-auto rounded-2xl border border-ink-border bg-[#172838] p-3 text-ink-foreground shadow-2xl lg:absolute lg:bottom-full lg:start-0 lg:mb-3">
                <div className="flex items-center gap-3 rounded-xl border border-ink-border bg-[#1d3041] p-4">
                  <span className="flex size-14 shrink-0 items-center justify-center rounded-full bg-[#65473f] text-xl font-bold text-white">{(name.trim()[0] || 'W').toUpperCase()}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-lg font-bold">{name || copy.student}</span>
                    <span className="block truncate text-sm text-ink-muted" dir="ltr">{email || copy.student}</span>
                  </span>
                </div>
                <button role="menuitem" type="button" onClick={() => { setAccountMenuOpen(false); onOpenProfile() }} className="mt-2 flex w-full items-center gap-3 rounded-xl px-3 py-3 text-start text-sm font-semibold text-ink-foreground transition hover:bg-white/5">
                  <UserRound className="size-5 text-violet-400" aria-hidden="true" />
                  <span className="flex-1">{copy.accountMenu.profile}</span>
                  <ChevronRight className="size-4 text-ink-muted rtl:rotate-180" aria-hidden="true" />
                </button>
                <button role="menuitem" type="button" onClick={() => { setAccountMenuOpen(false); onOpenSettings() }} className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-start text-sm font-semibold text-ink-foreground transition hover:bg-white/5">
                  <Settings className="size-5 text-violet-400" aria-hidden="true" />
                  <span className="flex-1">{copy.accountMenu.settings}</span>
                  <ChevronRight className="size-4 text-ink-muted rtl:rotate-180" aria-hidden="true" />
                </button>
                <div className="my-2 border-t border-ink-border" />
                <button role="menuitem" type="button" onClick={() => { setAccountMenuOpen(false); onSignOut() }} className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-start text-sm font-bold text-red-300 transition hover:bg-red-500/10">
                  <LogOut className="size-5 rtl:rotate-180" aria-hidden="true" />{signOutLabel}
                </button>
              </div>
            )}
          </div>
        </div>
      </aside>
    </>
  )
}
