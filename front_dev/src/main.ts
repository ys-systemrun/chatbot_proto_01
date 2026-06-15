import { ask, deleteSession } from './api'
import type { AskResponse } from './types'
import './style.css'

// ── DOM 参照 ────────────────────────────────────────────────
const messagesEl = document.getElementById('messages') as HTMLDivElement
const sessionIdDisplay = document.getElementById('session-id-display') as HTMLElement
const resetBtn = document.getElementById('reset-btn') as HTMLButtonElement
const chatForm = document.getElementById('chat-form') as HTMLFormElement
const inputEl = document.getElementById('input') as HTMLTextAreaElement
const sendBtn = document.getElementById('send-btn') as HTMLButtonElement

// ── 状態 ────────────────────────────────────────────────────
let sessionId: string | null = null

// ── ユーティリティ ───────────────────────────────────────────

function updateSessionDisplay(): void {
  sessionIdDisplay.textContent = sessionId ?? '（未開始）'
  sessionIdDisplay.title = sessionId ?? ''
}

/**
 * チャット欄にメッセージを追加する。
 * role が 'assistant' のときは rawResponse の JSON を折りたたんで表示する。
 */
function appendMessage(
  role: 'user' | 'assistant' | 'error',
  text: string,
  rawResponse?: AskResponse,
): void {
  const wrap = document.createElement('div')
  wrap.className = `message ${role}`

  const label = document.createElement('span')
  label.className = 'label'
  label.textContent = role === 'user' ? 'あなた' : role === 'error' ? 'エラー' : 'アシスタント'

  const content = document.createElement('p')
  content.className = 'content'
  content.textContent = text

  wrap.appendChild(label)
  wrap.appendChild(content)

  // デバッグ用: API レスポンスの生 JSON を折りたたんで表示
  if (role === 'assistant' && rawResponse) {
    const details = document.createElement('details')
    details.className = 'raw-response'

    const summary = document.createElement('summary')
    summary.textContent = 'API レスポンス (JSON)'

    const pre = document.createElement('pre')
    pre.textContent = JSON.stringify(rawResponse, null, 2)

    details.appendChild(summary)
    details.appendChild(pre)
    wrap.appendChild(details)
  }

  messagesEl.appendChild(wrap)
  messagesEl.scrollTop = messagesEl.scrollHeight
}

function appendLoading(): HTMLDivElement {
  const div = document.createElement('div')
  div.className = 'message assistant loading'
  div.innerHTML = '<span class="label">アシスタント</span><p class="content">...</p>'
  messagesEl.appendChild(div)
  messagesEl.scrollTop = messagesEl.scrollHeight
  return div
}

function setInputDisabled(disabled: boolean): void {
  inputEl.disabled = disabled
  sendBtn.disabled = disabled
  resetBtn.disabled = disabled
  sendBtn.textContent = disabled ? '送信中…' : '送信'
}

// ── イベントハンドラ ─────────────────────────────────────────

resetBtn.addEventListener('click', async () => {
  if (sessionId) {
    await deleteSession(sessionId).catch(() => {/* 無視 */})
    sessionId = null
  }
  messagesEl.innerHTML = ''
  updateSessionDisplay()
  inputEl.focus()
})

chatForm.addEventListener('submit', async (e) => {
  e.preventDefault()

  const text = inputEl.value.trim()
  if (!text) return

  appendMessage('user', text)
  inputEl.value = ''
  setInputDisabled(true)

  const loadingEl = appendLoading()

  try {
    const res = await ask({ session_id: sessionId, text })
    sessionId = res.session_id
    updateSessionDisplay()
    loadingEl.remove()
    appendMessage('assistant', res.answer, res)
  } catch (err) {
    loadingEl.remove()
    appendMessage('error', String(err))
  } finally {
    setInputDisabled(false)
    inputEl.focus()
  }
})

// Ctrl+Enter / Cmd+Enter でも送信
inputEl.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    chatForm.dispatchEvent(new Event('submit', { bubbles: true }))
  }
})

// ── 初期化 ───────────────────────────────────────────────────
updateSessionDisplay()
