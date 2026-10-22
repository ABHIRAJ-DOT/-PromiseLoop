import { Mic, MicOff } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { Button } from "@/components/ui/button"

type SpeechRecognitionLike = {
  lang: string
  interimResults: boolean
  continuous: boolean
  start: () => void
  stop: () => void
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null
  onerror: ((event: unknown) => void) | null
  onend: (() => void) | null
}

function getRecognition(): SpeechRecognitionLike | null {
  const w = window as unknown as {
    SpeechRecognition?: new () => SpeechRecognitionLike
    webkitSpeechRecognition?: new () => SpeechRecognitionLike
  }
  const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition
  return Ctor ? new Ctor() : null
}

export function MicButton({
  onTranscript,
  disabled,
}: {
  onTranscript: (text: string) => void
  disabled?: boolean
}) {
  const [listening, setListening] = useState(false)
  const [unsupported, setUnsupported] = useState(false)
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null)

  useEffect(() => {
    return () => {
      try {
        recognitionRef.current?.stop()
      } catch {
        /* already stopped */
      }
    }
  }, [])

  if (unsupported) return null

  const toggle = () => {
    if (listening) {
      recognitionRef.current?.stop()
      setListening(false)
      return
    }

    const recognition = getRecognition()
    if (!recognition) {
      setUnsupported(true)
      return
    }

    recognition.lang = navigator.language || "en-US"
    recognition.interimResults = false
    recognition.continuous = false
    recognition.onresult = (event) => {
      const transcript = Array.from({ length: event.results.length })
        .map((_, index) => event.results[index][0]?.transcript ?? "")
        .join(" ")
      if (transcript.trim()) onTranscript(transcript.trim())
    }
    recognition.onerror = () => setListening(false)
    recognition.onend = () => setListening(false)

    recognitionRef.current = recognition
    recognition.start()
    setListening(true)
  }

  return (
    <Button
      type="button"
      size="icon"
      variant={listening ? "destructive" : "outline"}
      disabled={disabled}
      onClick={toggle}
      title={listening ? "Stop listening" : "Speak your promise"}
    >
      {listening ? <MicOff className="size-4" /> : <Mic className="size-4" />}
    </Button>
  )
}
