import { useEffect, useRef, useState } from 'react'
import { STT_MODE } from './api.js'

// browser: Web Speech API, режим "микрофон всегда включён":
//   слушает, пока не нажмут снова; каждая законченная фраза -> onFinal(text);
//   Chrome сам гасит распознавание после тишины - перезапускаем.
// server: запись MediaRecorder одной фразой -> onAudio(blob), бэк сам распознаёт.
export function useSpeech({ lang, onFinal, onAudio }) {
  const [listening, setListening] = useState(false)
  const [interim, setInterim] = useState('')
  const [error, setError] = useState('')
  const recRef = useRef(null)
  const live = useRef(false) // пользователь хочет, чтобы микрофон был включён
  const chunks = useRef([])
  const cb = useRef({ onFinal, onAudio })
  cb.current = { onFinal, onAudio }

  const SR = typeof window !== 'undefined' && (window.SpeechRecognition || window.webkitSpeechRecognition)
  const supported = STT_MODE === 'server' ? !!navigator.mediaDevices : !!SR

  useEffect(() => () => { live.current = false; recRef.current?.stop?.() }, [])

  // смена языка на лету: перезапуск с новым языком
  useEffect(() => {
    if (live.current && STT_MODE !== 'server') recRef.current?.stop()
  }, [lang])

  function startBrowser() {
    const rec = new SR()
    rec.lang = lang === 'kz' ? 'kk-KZ' : 'ru-RU'
    rec.interimResults = true
    rec.continuous = true
    rec.onresult = (e) => {
      let mid = ''
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript
        if (e.results[i].isFinal) {
          if (t.trim()) cb.current.onFinal(t.trim())
        } else mid += t
      }
      setInterim(mid)
    }
    rec.onerror = (e) => {
      if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
        live.current = false
        setError('Нет доступа к микрофону')
      } else if (e.error !== 'no-speech' && e.error !== 'aborted') setError('Микрофон: ' + e.error)
    }
    rec.onend = () => {
      setInterim('')
      if (live.current) {
        setTimeout(() => { if (live.current) { try { startBrowser() } catch { /* уже запущен */ } } }, 150)
      } else setListening(false)
    }
    rec.start()
    recRef.current = rec
  }

  async function start() {
    setError('')
    setInterim('')
    if (STT_MODE === 'server') {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        const type = ['audio/webm', 'audio/mp4', 'audio/ogg'].find((t) => MediaRecorder.isTypeSupported(t)) || ''
        const rec = new MediaRecorder(stream, type ? { mimeType: type } : undefined)
        chunks.current = []
        rec.ondataavailable = (e) => e.data.size && chunks.current.push(e.data)
        rec.onstop = () => {
          stream.getTracks().forEach((t) => t.stop())
          setListening(false)
          cb.current.onAudio(new Blob(chunks.current, { type: rec.mimeType || 'audio/webm' }))
        }
        rec.start()
        recRef.current = rec
        setListening(true)
      } catch {
        setError('Нет доступа к микрофону')
      }
      return
    }
    if (!SR) { setError('Браузер не поддерживает распознавание речи. Откройте в Chrome.'); return }
    live.current = true
    setListening(true)
    startBrowser()
  }

  function stop() {
    live.current = false
    setListening(false)
    recRef.current?.stop()
  }

  return { listening, interim, error, supported, handsFree: STT_MODE !== 'server', start, stop, toggle: () => (listening ? stop() : start()) }
}
