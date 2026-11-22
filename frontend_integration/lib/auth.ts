'use client'

// Student account on the TRACE engine (POST /api/v1/auth/register|login, GET/PUT /api/v1/students/me[/profile]).
// The password is sent once to the local engine, which stores only a salted PBKDF2 hash; the browser keeps only the
// session token (localStorage) so a reload keeps the student signed in.
import type { StudentProfile } from '@/components/onboarding/options'

const KEY = 'wasla.auth'
export type AuthSession = { token: string; studentId: string; email: string }
export type AuthErrorCode = 'email_invalid' | 'password_short' | 'email_taken' | 'bad_credentials' | 'bad_token' | 'network'

export class AuthFailure extends Error {
  constructor(public code: AuthErrorCode) {
    super(code)
  }
}

export function savedSession(): AuthSession | null {
  try {
    const raw = window.localStorage.getItem(KEY)
    return raw ? (JSON.parse(raw) as AuthSession) : null
  } catch {
    return null
  }
}

function keep(s: AuthSession | null) {
  try {
    if (s) window.localStorage.setItem(KEY, JSON.stringify(s))
    else window.localStorage.removeItem(KEY)
  } catch { /* storage unavailable */ }
}

export function authHeader(): Record<string, string> {
  const s = savedSession()
  return s ? { Authorization: `Bearer ${s.token}` } : {}
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  let r: Response
  try {
    r = await fetch(`/engine${path}`, { ...init, headers: { 'Content-Type': 'application/json', ...authHeader(), ...(init.headers ?? {}) }, cache: 'no-store' })
  } catch {
    throw new AuthFailure('network')
  }
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new AuthFailure((typeof data.detail === 'string' ? data.detail : 'network') as AuthErrorCode)
  return data as T
}

type AuthResult = { token: string; student_id: string; email: string; profile: Partial<StudentProfile> }

// the engine keeps the profile without the email (it has its own column)
export function profileForEngine(p: StudentProfile) {
  const { email: _email, ...rest } = p
  return rest
}

export async function register(email: string, password: string, profile?: Partial<StudentProfile>) {
  const r = await call<AuthResult>('/auth/register', { method: 'POST', body: JSON.stringify({ email, password, profile }) })
  keep({ token: r.token, studentId: r.student_id, email: r.email })
  return r
}

export async function login(email: string, password: string) {
  const r = await call<AuthResult>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })
  keep({ token: r.token, studentId: r.student_id, email: r.email })
  return r
}

export async function me() {
  return call<{ student_id: string; email: string; profile: Partial<StudentProfile> }>('/students/me')
}

export async function saveProfile(profile: StudentProfile) {
  if (!savedSession()) return null
  return call<{ profile: Partial<StudentProfile> }>('/students/me/profile', { method: 'PUT', body: JSON.stringify({ profile: profileForEngine(profile) }) })
}

export function signOut() {
  keep(null)
}

// onboarding is done when the four learning preferences are saved
export function hasPreferences(p: Partial<StudentProfile>) {
  return Boolean(p.explanationStyle && p.informationAmount && p.learningEnvironment && p.questionTiming)
}
