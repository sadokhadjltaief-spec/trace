'use client'

import { useState, type FormEvent } from 'react'
import { ArrowRight, AtSign, Eye, EyeOff, Lock, Sparkles, ChevronDown, Settings2, Mail, LogOut, X, Sun, Moon, Monitor, Shield, Trash2, Send, CheckCircle2 } from 'lucide-react'
import { WaslaLogo } from '@/components/wasla-logo'
import { LanguageSwitcher } from '@/components/language-switcher'
import { ThemeToggle } from '@/components/theme-toggle'
import { DASHBOARD_COPY } from '@/components/dashboard/dashboard-copy'
import { useI18n } from '@/lib/i18n'
import { cn } from '@/lib/utils'
import { AuthFailure, login, register, type AuthErrorCode } from '@/lib/auth'
import type { StudentProfile } from '@/components/onboarding/options'

type Mode = 'login' | 'signup'
type ErrorKey = 'errorEmail' | 'errorPassword' | null

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

const SERVER_ERRORS: Record<string, Record<AuthErrorCode, string>> = {
  fr: { email_invalid: 'Adresse e-mail invalide.', password_short: 'Le mot de passe doit contenir au moins 8 caractères.', email_taken: 'Un compte existe déjà avec cet e-mail. Connecte-toi.', bad_credentials: 'E-mail ou mot de passe incorrect.', bad_token: 'Session expirée. Reconnecte-toi.', network: 'Le serveur WASLA ne répond pas. Vérifie qu’il est lancé.' },
  en: { email_invalid: 'Invalid email address.', password_short: 'Password must contain at least 8 characters.', email_taken: 'An account already exists with this email. Sign in.', bad_credentials: 'Wrong email or password.', bad_token: 'Session expired. Sign in again.', network: 'The WASLA server is not answering. Check that it is running.' },
  ar: { email_invalid: 'بريد إلكتروني غير صالح.', password_short: 'يجب أن تحتوي كلمة المرور على 8 أحرف على الأقل.', email_taken: 'يوجد حساب بهذا البريد. سجّل الدخول.', bad_credentials: 'البريد أو كلمة المرور غير صحيحة.', bad_token: 'انتهت الجلسة. سجّل الدخول من جديد.', network: 'خادم وصلة لا يستجيب. تأكد من تشغيله.' },
}

export function LoginScreen({ onSuccess }: { onSuccess: (r: { email: string; profile: Partial<StudentProfile> }) => void }) {
  const { t, lang } = useI18n()
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [errorKey, setErrorKey] = useState<ErrorKey>(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const [panel, setPanel] = useState<'contact' | 'settings' | null>(null)
  const [settingsTab, setSettingsTab] = useState<'profile' | 'preferences' | 'account'>('profile')
  const [messageSent, setMessageSent] = useState(false)
  const [notifications, setNotifications] = useState(true)
  const [privateMode, setPrivateMode] = useState(false)
  const [deleteConfirmation, setDeleteConfirmation] = useState('')
  const [serverError, setServerError] = useState('')
  const [busy, setBusy] = useState(false)
  // fields stay read-only until focused: the browser cannot fill in a saved email or password by itself
  const [armed, setArmed] = useState(false)

  const isLogin = mode === 'login'
  const error = errorKey ? t.login[errorKey] : serverError

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!EMAIL_PATTERN.test(email.trim())) {
      setErrorKey('errorEmail')
      return
    }
    if (password.length < 8) {
      setErrorKey('errorPassword')
      return
    }
    setErrorKey(null)
    setServerError('')
    setBusy(true)
    try {
      const r = isLogin ? await login(email.trim(), password) : await register(email.trim(), password)
      setPassword('')
      onSuccess({ email: r.email, profile: r.profile })
    } catch (e) {
      const code = e instanceof AuthFailure ? e.code : 'network'
      setServerError((SERVER_ERRORS[lang] ?? SERVER_ERRORS.fr)[code] ?? SERVER_ERRORS.fr.network)
    } finally {
      setBusy(false)
    }
  }

  function switchMode() {
    setMode(isLogin ? 'signup' : 'login')
    setErrorKey(null)
    setServerError('')
  }

  return (
    <main className="flex min-h-dvh flex-col bg-background text-foreground transition-colors md:flex-row">
      <section className="relative flex flex-1 items-center justify-center bg-background px-6 py-16 text-foreground transition-colors">
        <div className="absolute end-4 top-4 flex items-center gap-2">
          <LanguageSwitcher />
          <ThemeToggle labels={DASHBOARD_COPY[lang].theme} tone="light" />
          <div className="relative">
            <button
              type="button"
              onClick={() => setMenuOpen((value) => !value)}
              aria-expanded={menuOpen}
              aria-haspopup="menu"
              aria-label={lang === 'ar' ? 'قائمة الحساب' : 'Account menu'}
              className="flex h-9 items-center gap-2 rounded-xl border border-border bg-card px-3 text-sm font-semibold text-foreground shadow-sm transition hover:border-primary/50"
            >
              <span className="flex size-6 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">{email.trim().charAt(0).toUpperCase() || 'W'}</span>
              <ChevronDown className="size-4" aria-hidden="true" />
            </button>
            {menuOpen && (
              <div role="menu" className="absolute end-0 top-12 z-20 w-72 overflow-hidden rounded-2xl border border-border bg-card p-2 text-card-foreground shadow-xl">
                <div className="flex items-center gap-3 rounded-xl bg-muted/60 p-3">
                  <span className="flex size-11 shrink-0 items-center justify-center rounded-full bg-primary text-lg font-bold text-primary-foreground">{email.trim().charAt(0).toUpperCase() || 'W'}</span>
                  <div className="min-w-0"><p className="font-semibold">{email ? email.split('@')[0] : (lang === 'ar' ? 'متعلم وصلة' : 'Wasla learner')}</p><p className="truncate text-xs text-muted-foreground" dir="ltr">{email || (lang === 'ar' ? 'لم يتم تسجيل الدخول' : 'Not signed in yet')}</p></div>
                </div>
                <button role="menuitem" type="button" onClick={() => { setPanel('contact'); setMessageSent(false); setMenuOpen(false) }} className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-start text-sm font-medium hover:bg-muted"><Mail className="size-4 text-primary" />{lang === 'ar' ? 'تواصل معنا' : 'Contact us'}</button>
                <button role="menuitem" type="button" onClick={() => { setPanel('settings'); setSettingsTab('profile'); setMenuOpen(false) }} className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-start text-sm font-medium hover:bg-muted"><Settings2 className="size-4 text-primary" />{lang === 'ar' ? 'الإعدادات' : 'Settings'}</button>
                <div className="my-1 border-t border-border" />
                <button role="menuitem" type="button" onClick={() => { setMenuOpen(false); setEmail(''); setPassword(''); setErrorKey(null); setMode('login') }} className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-start text-sm font-semibold text-destructive hover:bg-destructive/10"><LogOut className="size-4" />{lang === 'ar' ? 'تسجيل الخروج' : 'Log out'}</button>
              </div>
            )}
          </div>
        </div>
        <div className="flex w-full max-w-sm flex-col">
          <WaslaLogo className="mx-auto mb-6 size-24 md:hidden" />

          <h1 className="bg-gradient-to-r from-[#f5a03f] via-primary to-[#f5a03f] bg-clip-text text-center text-4xl font-bold text-transparent text-balance">
            {isLogin ? t.login.titleLogin : t.login.titleSignup}
          </h1>
          <p className="mt-3 text-center text-sm text-muted-foreground">
            {isLogin ? t.login.noAccount : t.login.haveAccount}{' '}
            <button
              type="button"
              onClick={switchMode}
              className="font-semibold text-foreground underline-offset-4 hover:text-primary hover:underline"
            >
              {isLogin ? t.login.createOne : t.login.signIn}
            </button>
          </p>

          <div className="mt-10 flex items-center gap-4" aria-hidden="true">
            <span className="h-px flex-1 bg-border" />
            <span className="text-sm font-semibold">{isLogin ? t.login.withEmailLogin : t.login.withEmailSignup}</span>
            <span className="h-px flex-1 bg-border" />
          </div>

          <form onSubmit={handleSubmit} noValidate autoComplete="off" className="mt-6 flex flex-col gap-3">
            <label htmlFor="email" className="sr-only">
              {t.login.email}
            </label>
            <div className="relative">
              <AtSign
                className="pointer-events-none absolute start-4 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden="true"
              />
              <input
                id="email"
                type="email"
                dir="ltr"
                name="wasla-email"
                autoComplete="off"
                readOnly={!armed}
                onFocus={() => setArmed(true)}
                placeholder={t.login.email}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                aria-invalid={Boolean(error) && !EMAIL_PATTERN.test(email.trim())}
                aria-describedby={error ? 'auth-error' : undefined}
                className="h-12 w-full rounded-xl border border-input bg-card pe-4 ps-11 text-start text-sm text-foreground placeholder:text-muted-foreground outline-none transition focus:border-primary focus:ring-3 focus:ring-primary/25 rtl:placeholder:text-right"
              />
            </div>

            <label htmlFor="password" className="sr-only">
              {t.login.password}
            </label>
            <div className="relative">
              <Lock
                className="pointer-events-none absolute start-4 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden="true"
              />
              <input
                id="password"
                type={showPassword ? 'text' : 'password'}
                name="wasla-password"
                autoComplete="new-password"
                readOnly={!armed}
                onFocus={() => setArmed(true)}
                placeholder={t.login.password}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-describedby={error ? 'auth-error' : undefined}
                className="h-12 w-full rounded-xl border border-input bg-card pe-12 ps-11 text-sm text-foreground placeholder:text-muted-foreground outline-none transition focus:border-primary focus:ring-3 focus:ring-primary/25"
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? t.login.hidePassword : t.login.showPassword}
                className="absolute end-2 top-1/2 flex size-8 -translate-y-1/2 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground"
              >
                {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>

            {isLogin && (
              <button type="button" className="self-end text-xs font-medium text-muted-foreground hover:text-primary">
                {t.login.forgot}
              </button>
            )}

            <p id="auth-error" role="alert" className={cn('min-h-5 text-sm text-red-400', !error && 'invisible')}>
              {error}
            </p>

            <button
              type="submit"
              disabled={busy}
              className="flex h-12 disabled:opacity-60 items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-primary to-primary-deep font-semibold text-white shadow-lg shadow-primary/20 transition hover:brightness-110 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-primary/40"
            >
              {isLogin ? t.login.submitLogin : t.login.submitSignup}
              <ArrowRight className="size-5 rtl:rotate-180" aria-hidden="true" />
            </button>
          </form>
        </div>
      </section>

      <aside className="relative hidden flex-1 flex-col items-center justify-center overflow-hidden bg-gradient-to-br from-[#f5a03f] via-primary to-primary-deep px-10 py-12 text-white md:flex">
        <div className="absolute -right-24 -top-24 size-72 rounded-full bg-white/10" aria-hidden="true" />
        <div className="absolute -bottom-32 -left-20 size-80 rounded-full bg-white/10" aria-hidden="true" />

        <div className="relative flex max-w-sm flex-col items-center text-center">
          <div className="rounded-3xl bg-white p-4 shadow-xl shadow-black/10">
            <WaslaLogo className="size-36" />
          </div>

          <div className="mt-10 flex size-14 items-center justify-center rounded-2xl bg-white/20 backdrop-blur-sm">
            <Sparkles className="size-6" aria-hidden="true" />
          </div>
          <h2 className="mt-5 text-2xl font-bold text-balance">{t.login.asideTitle}</h2>
          <p className="mt-3 text-sm leading-relaxed text-white/90 text-pretty">{t.login.asideText}</p>
        </div>
      </aside>

      {panel && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-0 backdrop-blur-sm sm:items-center sm:p-5" onMouseDown={(event) => { if (event.target === event.currentTarget) setPanel(null) }}>
          <section role="dialog" aria-modal="true" aria-labelledby="panel-title" className="max-h-[92dvh] w-full max-w-2xl overflow-y-auto rounded-t-3xl border border-border bg-background p-5 text-foreground shadow-2xl sm:rounded-3xl sm:p-8">
            <header className="mb-6 flex items-start justify-between gap-4">
              <div className="flex items-center gap-3">
                <span className="flex size-11 items-center justify-center rounded-2xl bg-primary/10 text-primary">{panel === 'contact' ? <Mail className="size-5" /> : <Settings2 className="size-5" />}</span>
                <div><h2 id="panel-title" className="text-xl font-bold">{panel === 'contact' ? (lang === 'ar' ? 'نحن هنا للمساعدة' : 'Let’s make learning better') : (lang === 'ar' ? 'إعداداتك' : 'Your settings')}</h2><p className="mt-1 text-sm text-muted-foreground">{panel === 'contact' ? (lang === 'ar' ? 'أرسل لنا ملاحظة أو سؤالاً.' : 'Questions, ideas, or a little feedback — we’re listening.') : (lang === 'ar' ? 'تحكم في تفضيلاتك وحسابك.' : 'A few thoughtful controls for your Wasla experience.')}</p></div>
              </div>
              <button type="button" onClick={() => setPanel(null)} aria-label={lang === 'ar' ? 'إغلاق' : 'Close'} className="flex size-9 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground hover:text-foreground"><X className="size-4" /></button>
            </header>

            {panel === 'contact' ? (
              messageSent ? (
                <div className="rounded-2xl border border-primary/20 bg-primary/5 px-6 py-10 text-center"><CheckCircle2 className="mx-auto size-10 text-primary" /><h3 className="mt-4 text-lg font-semibold">{lang === 'ar' ? 'وصلتنا رسالتك' : 'Message ready to go'}</h3><p className="mt-2 text-sm text-muted-foreground">{lang === 'ar' ? 'شكراً لمساعدتنا في تطوير وصلة.' : 'Thanks for helping us make Wasla a little more useful.'}</p><button type="button" onClick={() => setPanel(null)} className="mt-5 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground">{lang === 'ar' ? 'تم' : 'Done'}</button></div>
              ) : (
                <form onSubmit={(event) => { event.preventDefault(); setMessageSent(true) }} className="flex flex-col gap-4">
                  <label className="text-sm font-medium" htmlFor="contact-email">{lang === 'ar' ? 'بريدك الإلكتروني' : 'Your email'}<input id="contact-email" type="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" dir="ltr" className="mt-2 h-11 w-full rounded-xl border border-input bg-card px-3 text-foreground outline-none focus:border-primary focus:ring-3 focus:ring-primary/20" /></label>
                  <label className="text-sm font-medium" htmlFor="contact-message">{lang === 'ar' ? 'ما الذي يدور في ذهنك؟' : 'What’s on your mind?'}<textarea id="contact-message" required rows={5} placeholder={lang === 'ar' ? 'اكتب رسالتك هنا...' : 'Share a question, an idea, or something we could improve…'} className="mt-2 w-full resize-y rounded-xl border border-input bg-card p-3 text-foreground outline-none focus:border-primary focus:ring-3 focus:ring-primary/20" /></label>
                  <button type="submit" className="flex h-12 items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-primary to-primary-deep font-semibold text-white shadow-lg shadow-primary/20"><Send className="size-4" />{lang === 'ar' ? 'إرسال الرسالة' : 'Send your note'}</button>
                  <p className="text-center text-xs text-muted-foreground">{lang === 'ar' ? 'كل فكرة تساعدنا على تحسين تجربة التعلم.' : 'Every note helps us shape a kinder, clearer learning space.'}</p>
                </form>
              )
            ) : (
              <div className="grid gap-5 sm:grid-cols-[170px_1fr]">
                <nav aria-label={lang === 'ar' ? 'أقسام الإعدادات' : 'Settings sections'} className="flex gap-2 overflow-x-auto sm:flex-col">
                  {(['profile', 'preferences', 'account'] as const).map((tab) => <button key={tab} type="button" onClick={() => setSettingsTab(tab)} aria-current={settingsTab === tab ? 'page' : undefined} className={cn('rounded-xl px-3 py-2.5 text-start text-sm font-semibold capitalize transition', settingsTab === tab ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-muted')}>{tab === 'profile' ? (lang === 'ar' ? 'الملف الشخصي' : 'Profile') : tab === 'preferences' ? (lang === 'ar' ? 'التفضيلات' : 'Preferences') : (lang === 'ar' ? 'الحساب' : 'Account')}</button>)}
                </nav>
                <div className="min-w-0">
                  {settingsTab === 'profile' ? <div><p className="text-xs font-semibold uppercase tracking-widest text-primary">Wasla learner</p><h3 className="mt-1 text-xl font-bold">{lang === 'ar' ? 'الملف الشخصي' : 'Profile'}</h3><p className="mt-1 text-sm text-muted-foreground">{lang === 'ar' ? 'معلومات الحساب الحالي.' : 'The details associated with this session.'}</p><div className="mt-5 flex items-center gap-4 rounded-2xl border border-border bg-card p-4"><span className="flex size-14 shrink-0 items-center justify-center rounded-full bg-primary text-xl font-bold text-primary-foreground">{email.trim().charAt(0).toUpperCase() || 'W'}</span><div className="min-w-0"><p className="font-semibold">{email ? email.split('@')[0] : (lang === 'ar' ? 'متعلم وصلة' : 'Wasla learner')}</p><p className="truncate text-sm text-muted-foreground" dir="ltr">{email || (lang === 'ar' ? 'أدخل بريدك عند تسجيل الدخول' : 'Add your email when you sign in')}</p></div></div><p className="mt-4 text-xs text-muted-foreground">{lang === 'ar' ? 'تظهر معلومات الملف الشخصي بعد تسجيل الدخول.' : 'Your profile details will be available after you sign in.'}</p></div> : settingsTab === 'preferences' ? <div><p className="text-xs font-semibold uppercase tracking-widest text-primary">Wasla</p><h3 className="mt-1 text-xl font-bold">{lang === 'ar' ? 'التفضيلات' : 'Preferences'}</h3><p className="mt-1 text-sm text-muted-foreground">{lang === 'ar' ? 'خصص طريقة ظهور التطبيق وعمله.' : 'Make the learning space feel right for you.'}</p>
                    <div className="mt-5 divide-y divide-border rounded-2xl border border-border px-4">
                      <div className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between"><div><p className="font-semibold">{lang === 'ar' ? 'المظهر' : 'Appearance'}</p><p className="text-sm text-muted-foreground">{lang === 'ar' ? 'اختر السمة المفضلة.' : 'Choose how Wasla looks on this device.'}</p></div><div className="flex rounded-xl bg-muted p-1">{([{ id: 'light', label: lang === 'ar' ? 'فاتح' : 'Light', Icon: Sun }, { id: 'dark', label: lang === 'ar' ? 'داكن' : 'Dark', Icon: Moon }, { id: 'system', label: lang === 'ar' ? 'النظام' : 'System', Icon: Monitor }] as const).map(({ id, label, Icon }) => <button key={id} type="button" aria-pressed={id === 'dark' ? document.documentElement.classList.contains('dark') : id === 'light' ? !document.documentElement.classList.contains('dark') : false} onClick={() => { const dark = id === 'dark' || (id === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches); document.documentElement.classList.toggle('dark', dark); try { if (id === 'system') localStorage.removeItem('wasla-theme'); else localStorage.setItem('wasla-theme', id) } catch {} }} className="flex items-center gap-1.5 rounded-lg px-2.5 py-2 text-xs font-semibold hover:bg-card aria-pressed:bg-card aria-pressed:text-primary"><Icon className="size-3.5" />{label}</button>)}</div></div>
                      <label className="flex cursor-pointer items-center justify-between gap-4 py-4"><span><span className="block font-semibold">{lang === 'ar' ? 'تحديثات مهمة' : 'Helpful updates'}</span><span className="text-sm text-muted-foreground">{lang === 'ar' ? 'إشعارات حول تقدمك.' : 'A nudge when there’s something worth knowing.'}</span></span><input type="checkbox" checked={notifications} onChange={(event) => setNotifications(event.target.checked)} className="size-5 accent-primary" /></label>
                      <label className="flex cursor-pointer items-center justify-between gap-4 py-4"><span><span className="block font-semibold"><Shield className="me-2 inline size-4 text-primary" />{lang === 'ar' ? 'وضع الخصوصية' : 'Private mode'}</span><span className="text-sm text-muted-foreground">{lang === 'ar' ? 'إخفاء الاسم في المساحات المشتركة.' : 'Keep your name out of shared learning spaces.'}</span></span><input type="checkbox" checked={privateMode} onChange={(event) => setPrivateMode(event.target.checked)} className="size-5 accent-primary" /></label>
                    </div>
                  </div> : <div><p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">{lang === 'ar' ? 'الأمان' : 'SECURITY'}</p><h3 className="mt-1 text-xl font-bold">{lang === 'ar' ? 'الحساب' : 'Account'}</h3><p className="mt-1 text-sm text-muted-foreground">{lang === 'ar' ? 'إدارة الوصول إلى مساحة التعلم الخاصة بك.' : 'Actions affecting your account access are gathered here.'}</p><div className="mt-5 rounded-2xl border border-destructive/20 bg-destructive/5 p-4"><div className="flex gap-3"><span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-destructive/10 text-destructive"><Trash2 className="size-5" /></span><div className="min-w-0 flex-1"><h4 className="font-semibold">{lang === 'ar' ? 'حذف الحساب' : 'Delete account'}</h4><p className="mt-1 text-sm text-muted-foreground">{lang === 'ar' ? 'ستؤدي إزالة هذه الجلسة إلى إعادتك لتسجيل الدخول.' : 'This demo will clear the current session and return you to login.'}</p><label htmlFor="delete-confirmation" className="sr-only">{lang === 'ar' ? 'اكتب DELETE للتأكيد' : 'Type DELETE to confirm'}</label><input id="delete-confirmation" value={deleteConfirmation} onChange={(event) => setDeleteConfirmation(event.target.value)} placeholder={lang === 'ar' ? 'اكتب DELETE' : 'Type DELETE'} className="mt-4 h-11 w-full rounded-xl border border-input bg-card px-3 text-foreground outline-none focus:border-primary focus:ring-3 focus:ring-primary/20" /><button type="button" disabled={deleteConfirmation !== 'DELETE'} onClick={() => { setEmail(''); setPassword(''); setDeleteConfirmation(''); setMode('login'); setPanel(null) }} className="mt-3 flex items-center gap-2 rounded-xl bg-destructive px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-45"><Trash2 className="size-4" />{lang === 'ar' ? 'حذف الحساب' : 'Delete account'}</button></div></div></div></div>}
                </div>
              </div>
            )}
          </section>
        </div>
      )}
    </main>
  )
}
