'use client'

import { useState } from 'react'
import { Check, Heart, Target } from 'lucide-react'
import { LearningPreferencesForm } from '@/components/onboarding/learning-preferences'
import type { StudentProfile } from '@/components/onboarding/options'
import { useI18n } from '@/lib/i18n'
import { DASHBOARD_COPY } from './dashboard-copy'
import { Sidebar, type NavId } from './sidebar'
import { Topbar } from './topbar'
import { QuickActions } from './quick-actions'
import { StreakCard } from './streak-card'
import { PointsCard } from './points-card'
import { ContentSection } from './content-section'
import { QuizSourcePicker } from './quiz-source-picker'
import { StudyPlanFlow } from './study-plan-flow'
import { SummaryFlow } from './summary-flow'
import { CurriculumView } from './curriculum-view'
import { ProgressView } from './progress-view'
import { MediaStudio } from './media-studio'
import type { ToolId } from './tools'
import { TutorView } from './tutor/tutor-view'
import type { TutorContext } from './tutor/tutor-chat'
import { useConversations } from './tutor/use-conversations'
import { AccountSettings, type SettingsSection } from './account-settings'
import { ProfilePage } from './profile-page'
import { SchoolGames } from './school-games'

type Props = {
  profile: StudentProfile
  onChange: (profile: StudentProfile) => void
  onSignOut: () => void
}

function timeOfDay(hour: number) {
  if (hour < 12) return 'morning' as const
  if (hour < 18) return 'afternoon' as const
  return 'evening' as const
}

export function Dashboard({ profile, onChange, onSignOut }: Props) {
  const { t, option, lang } = useI18n()
  const copy = DASHBOARD_COPY[lang]
  const [active, setActive] = useState<NavId>('home')
  const [activeTool, setActiveTool] = useState<ToolId | null>(null)
  const [quizOpen, setQuizOpen] = useState(false)
  const [gamesOpen, setGamesOpen] = useState(false)
  const [flashcardsOpen, setFlashcardsOpen] = useState(false)
  const [summaryOpen, setSummaryOpen] = useState(false)
  const [planOpen, setPlanOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [settingsSection, setSettingsSection] = useState<SettingsSection>('profile')
  const [profilePageOpen, setProfilePageOpen] = useState(false)
  const [now] = useState(() => new Date())

  const firstName = profile.name.trim().split(/\s+/)[0] || copy.student
  const todayIndex = (now.getDay() + 6) % 7
  const minutesByDay = Array.from({ length: 7 }, (_, i) => (i === todayIndex ? 5 : 0))
  const streak = 1
  // gamified mode: points come only from genuine progress the tutor observed (10 per notion shown understood)
  const [points, setPoints] = useState(0)
  const [programmeQuery, setProgrammeQuery] = useState<{ q: string; at: number } | null>(null)

  const preferences = [
    { key: 'explanations', label: t.summary.explanations, value: option('explanation', profile.explanationStyle)?.label },
    { key: 'information', label: t.summary.information, value: option('info', profile.informationAmount)?.label },
    { key: 'environment', label: t.summary.environment, value: option('environment', profile.learningEnvironment)?.label },
    { key: 'timing', label: t.summary.timing, value: option('timing', profile.questionTiming)?.label },
  ]

  const openSettings = (section: SettingsSection = 'profile') => {
    setSettingsSection(section)
    setSettingsOpen(true)
    setProfilePageOpen(false)
    setMenuOpen(false)
  }

  const navigate = (id: NavId) => {
    setQuizOpen(false)
    setGamesOpen(false)
    setFlashcardsOpen(false)
    setSummaryOpen(false)
    setPlanOpen(false)
    setActiveTool(null)
    setActive(id)
    setMenuOpen(false)
    setProfilePageOpen(false)
    if (id === 'preferences') {
      openSettings('preferences')
      return
    }
    if (id === 'content') {
      requestAnimationFrame(() => document.getElementById('my-content')?.scrollIntoView({ behavior: 'smooth' }))
    } else {
      window.scrollTo({ top: 0 })
    }
  }

  const openTool = (id: ToolId) => {
    setQuizOpen(false)
    setGamesOpen(false)
    setFlashcardsOpen(false)
    setSummaryOpen(false)
    setPlanOpen(false)
    if (id === 'tutor') navigate('tutor')
    else if (id === 'flashcards') {
      setActive('home')
      setActiveTool('flashcards')
      setFlashcardsOpen(true)
      setQuizOpen(false)
      setSummaryOpen(false)
      setPlanOpen(false)
      setMenuOpen(false)
      window.scrollTo({ top: 0 })
    } else if (id === 'summary') {
      setActive('home')
      setActiveTool('summary')
      setSummaryOpen(true)
      setQuizOpen(false)
      setFlashcardsOpen(false)
      setPlanOpen(false)
      setMenuOpen(false)
      window.scrollTo({ top: 0 })
    } else if (id === 'quiz') {
      setActive('home')
      setActiveTool('quiz')
      setQuizOpen(true)
      setPlanOpen(false)
      setMenuOpen(false)
      window.scrollTo({ top: 0 })
    } else if (id === 'plan') {
      setActive('home')
      setActiveTool('plan')
      setQuizOpen(false)
      setPlanOpen(true)
      setMenuOpen(false)
      window.scrollTo({ top: 0 })
    } else setMenuOpen(false)
  }

  const conversations = useConversations()
  const tutorContext: TutorContext = {
    name: firstName,
    level: option('education', profile.educationLevel)?.label ?? '',
    explanations: preferences[0].value ?? '',
    information: preferences[1].value ?? '',
    environment: preferences[2].value ?? '',
    timing: preferences[3].value ?? '',
    prefs: {
      explanationStyle: profile.explanationStyle,
      informationAmount: profile.informationAmount,
      learningEnvironment: profile.learningEnvironment,
      questionTiming: profile.questionTiming,
    },
    onProgress: (n: number) => { if (profile.learningEnvironment === 'gamified') setPoints((x) => x + 10 * n) },
  }

  return (
    <div className="flex min-h-dvh bg-muted/40">
      <Sidebar
        copy={copy}
        active={active}
        onNavigate={navigate}
        onTool={openTool}
        activeTool={activeTool}
        showGames={profile.educationLevel === 'school'}
        gamesActive={gamesOpen}
        onOpenGames={() => { setGamesOpen(true); setQuizOpen(false); setFlashcardsOpen(false); setSummaryOpen(false); setPlanOpen(false); setActiveTool(null); setActive('home'); setMenuOpen(false); window.scrollTo({ top: 0 }) }}
        name={profile.name}
        email={profile.email}
        signOutLabel={t.dashboard.signOut}
        onSignOut={onSignOut}
        onOpenProfile={() => { setProfilePageOpen(true); setActive('home'); setMenuOpen(false) }}
        onOpenSettings={() => openSettings('profile')}
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
      />

      {active === 'tutor' ? (
        <TutorView
          lang={lang}
          firstName={firstName}
          context={tutorContext}
          openMenuLabel={copy.openMenu}
          onOpenMenu={() => setMenuOpen(true)}
          onGoHome={() => navigate('home')}
          store={conversations}
        />
      ) : (
      <div className="flex min-w-0 flex-1 flex-col">
        {!quizOpen && !gamesOpen && !flashcardsOpen && !summaryOpen && !planOpen ? <Topbar copy={copy} streak={streak} points={points} onOpenMenu={() => setMenuOpen(true)} onSearch={(q) => { setProgrammeQuery({ q, at: Date.now() }); navigate('curriculum') }} /> : null}

        {profilePageOpen ? (
          <ProfilePage profile={profile} onEdit={() => openSettings('profile')} onBack={() => setProfilePageOpen(false)} />
        ) : (
        <main className={quizOpen || gamesOpen || flashcardsOpen || summaryOpen ? 'w-full' : 'mx-auto flex w-full max-w-6xl flex-col gap-8 px-4 py-8 md:px-8'}>
          {gamesOpen ? (
            <SchoolGames lang={lang} onBack={() => setGamesOpen(false)} />
          ) : quizOpen ? (
            <QuizSourcePicker copy={copy} onBack={() => { setQuizOpen(false); setActiveTool(null) }} lang={lang} />
          ) : flashcardsOpen ? (
            <QuizSourcePicker copy={copy} onBack={() => { setFlashcardsOpen(false); setActiveTool(null) }} kind="flashcards" lang={lang} />
          ) : summaryOpen ? (
            <SummaryFlow lang={lang} onBack={() => { setSummaryOpen(false); setActiveTool(null) }} />
          ) : planOpen ? (
            <StudyPlanFlow copy={copy} onBack={() => { setPlanOpen(false); setActiveTool(null) }} lang={lang} />
          ) : active === 'preferences' ? (
            <section aria-labelledby="settings-title" className="flex flex-col gap-6 rounded-2xl border border-border bg-card p-5 md:p-8">
              <div className="flex flex-col gap-1">
                <h1 id="settings-title" className="text-2xl font-bold text-foreground">
                  {t.dashboard.prefsTitle}
                </h1>
                <p className="text-muted-foreground">{t.dashboard.savedInstantly}</p>
              </div>
              <LearningPreferencesForm
                value={profile}
                onChange={(key, id) => onChange({ ...profile, [key]: id })}
                notes={profile.notes}
                onNoteChange={(key, note) => onChange({ ...profile, notes: { ...profile.notes, [key]: note } })}
              />
            </section>
          ) : active === 'curriculum' ? (
            <CurriculumView lang={lang} search={programmeQuery} />
          ) : active === 'progress' ? (
            <ProgressView lang={lang} />
          ) : active === 'media' ? (
            <MediaStudio lang={lang} />
          ) : active === 'content' ? (
            <ContentSection copy={copy} />
          ) : (
            <>
              <section className="flex flex-col gap-1">
                <h1 className="text-balance text-3xl font-bold tracking-tight text-foreground md:text-4xl">
                  {copy.greeting(timeOfDay(now.getHours()), firstName)}
                </h1>
                <p className="text-pretty text-muted-foreground">{copy.overview}</p>
              </section>

              <QuickActions copy={copy} onSelect={openTool} educationLevel={profile.educationLevel} onOpenGames={() => { setGamesOpen(true); setActiveTool(null); setActive('home'); setMenuOpen(false); window.scrollTo({ top: 0 }) }} />

              <section className="flex flex-col gap-4 rounded-2xl bg-gradient-to-br from-primary to-primary-deep p-6 text-primary-foreground md:flex-row md:items-center md:gap-8">
                  <span className="flex size-10 items-center justify-center rounded-xl bg-white/20">
                    <Target className="size-5" aria-hidden="true" />
                  </span>
                  <div className="flex flex-col gap-1">
                    <h2 className="text-xl font-bold">{copy.goal.title}</h2>
                    <p className="text-sm text-primary-foreground/90">
                      {option('goal', profile.dailyGoal)?.label} &middot; {option('education', profile.educationLevel)?.label}
                    </p>
                  </div>
                  <div
                    className="h-2.5 flex-1 overflow-hidden rounded-full bg-white/25"
                    role="progressbar"
                    aria-label={t.dashboard.goalProgress}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={0}
                  >
                    <div className="h-full w-0 rounded-full bg-white" />
                  </div>
                  <p className="text-sm text-primary-foreground/90">{t.dashboard.minDone}</p>
                  <ul className="flex flex-1 flex-col gap-1.5 border-t border-white/20 pt-4 md:border-s md:border-t-0 md:ps-8 md:pt-0">
                    {preferences.map((p) => (
                      <li key={p.key} className="flex items-start gap-2 text-sm">
                        <Check className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                        <span>
                          <span className="text-primary-foreground/80">{p.label}: </span>
                          <span className="font-semibold">{p.value}</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                  <button
                    type="button"
                    onClick={() => navigate('preferences')}
                    className="self-start text-sm font-semibold underline-offset-4 hover:underline"
                  >
                    {copy.goal.edit}
                  </button>
              </section>

              <section aria-label={copy.dashboardStats} className="grid gap-4 xl:grid-cols-[1.45fr_1fr]">
                <StreakCard copy={copy} minutesByDay={minutesByDay} todayIndex={todayIndex} streak={streak} best={streak} />
                <PointsCard copy={copy} points={points} />
              </section>

              <a href="mailto:?subject=Feedback%20about%20Wasla" className="mx-auto inline-flex items-center gap-2 py-2 font-medium text-muted-foreground transition hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                <Heart className="size-4 fill-current" aria-hidden="true" />
                {copy.feedback}
              </a>
            </>
          )}
        </main>
        )}
      </div>
      )}
      {settingsOpen ? (
        <AccountSettings
          profile={profile}
          onChange={onChange}
          initialSection={settingsSection}
          onClose={() => { setSettingsOpen(false); setActive('home') }}
          onDeleteAccount={onSignOut}
        />
      ) : null}
    </div>
  )
}
