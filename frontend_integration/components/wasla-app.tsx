'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { LoginScreen } from '@/components/auth/login-screen'
import { OnboardingFlow } from '@/components/onboarding/onboarding-flow'
import { Dashboard } from '@/components/dashboard/dashboard'
import { WelcomeTransition } from '@/components/onboarding/welcome-transition'
import type { StudentProfile } from '@/components/onboarding/options'
import { I18nProvider, useI18n } from '@/lib/i18n'
import { hasPreferences, me, saveProfile, savedSession, signOut } from '@/lib/auth'

const EMPTY_PROFILE: StudentProfile = {
  email: '',
  name: '',
  educationLevel: null,
  explanationStyle: null,
  informationAmount: null,
  learningEnvironment: null,
  questionTiming: null,
  dailyGoal: null,
  notes: {},
}

type Stage = 'loading' | 'login' | 'onboarding' | 'welcome' | 'dashboard'

export function WaslaApp() {
  return (
    <I18nProvider>
      <WaslaStages />
    </I18nProvider>
  )
}

function WaslaStages() {
  const { lang } = useI18n()
  const [stage, setStage] = useState<Stage>('loading')
  const [profile, setProfile] = useState<StudentProfile>(EMPTY_PROFILE)
  const saveTimer = useRef<number | null>(null)

  // the profile (onboarding preferences included) lives in the engine's database: changes are saved, a reload or a
  // new login restores them, and the tutor reads them at every turn
  const update = useCallback((next: StudentProfile) => {
    setProfile(next)
    if (saveTimer.current) window.clearTimeout(saveTimer.current)
    saveTimer.current = window.setTimeout(() => { saveProfile({ ...next, lang } as StudentProfile).catch(() => {}) }, 400)
  }, [lang])

  const enter = useCallback((email: string, saved: Partial<StudentProfile>) => {
    const p = { ...EMPTY_PROFILE, ...saved, notes: saved.notes ?? {}, email }
    setProfile(p)
    setStage(hasPreferences(p) && p.name ? 'dashboard' : 'onboarding')
  }, [])

  useEffect(() => {
    if (!savedSession()) { setStage('login'); return }
    me().then((r) => enter(r.email, r.profile)).catch(() => { signOut(); setStage('login') })
  }, [enter])

  if (stage === 'loading') return <div className="min-h-dvh bg-background" />

  if (stage === 'login') {
    return <LoginScreen onSuccess={(r) => enter(r.email, r.profile)} />
  }

  if (stage === 'onboarding') {
    return (
      <OnboardingFlow
        profile={profile}
        onChange={setProfile}
        onComplete={() => { saveProfile({ ...profile, lang } as StudentProfile).catch(() => {}); setStage('welcome') }}
      />
    )
  }

  if (stage === 'welcome') {
    return <WelcomeTransition firstName={profile.name.trim().split(/\s+/)[0] || ''} lang={lang} onComplete={() => setStage('dashboard')} />
  }

  return (
    <Dashboard
      profile={profile}
      onChange={update}
      onSignOut={() => {
        signOut()
        setProfile(EMPTY_PROFILE)
        setStage('login')
      }}
    />
  )
}
