import { useState, useRef, useEffect, useCallback } from "react";
import VideoAnalyzer from "./VideoAnalyzer";
import { LoadingSpinner } from "./ui/LoadingSpinner";
import { toast } from "sonner";
import {
  Video,
  Camera,
  Headphones,
  FileText,
  Lightbulb,
  Star,
  Mic,
  Square,
  Sparkles,
  RotateCcw,
  AlertTriangle,
  Clock,
  CheckCircle2,
  Circle,
  Eye,
  Keyboard,
  Volume2,
} from "lucide-react";

// TypeScript declarations for Web Speech API
interface SpeechRecognitionEvent {
  resultIndex: number;
  results: SpeechRecognitionResultList;
}

interface SpeechRecognitionResultList {
  length: number;
  item(index: number): SpeechRecognitionResult;
  [index: number]: SpeechRecognitionResult;
}

interface SpeechRecognitionResult {
  isFinal: boolean;
  length: number;
  item(index: number): SpeechRecognitionAlternative;
  [index: number]: SpeechRecognitionAlternative;
}

interface SpeechRecognitionAlternative {
  transcript: string;
  confidence: number;
}

interface SpeechRecognition extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
}

declare global {
  interface Window {
    SpeechRecognition: new () => SpeechRecognition;
    webkitSpeechRecognition: new () => SpeechRecognition;
  }
}

interface Question {
  id: number;
  question: string;
  keywords: string[];
  ideal_answer?: string;
  difficulty?: string;
  time_limit_seconds?: number;
  questionNumber?: number;
  totalQuestions?: number;
  domain?: string;
  category?: string;
}

interface VideoMetrics {
  eyeContactPercent: number;
  dominantExpression: string;
  movementStability: number;
  overallConfidence: number;
}

interface RecorderProps {
  question: Question;
  jobDescription?: string;
  userId: string;  // Required: User's UUID
  sessionId: string;  // Required: Session UUID
  questionOrder: number;  // Position in session (1-10)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onRecordingComplete: (feedback: any) => void;
  onSkip?: () => void;  // Handler for skipping question
  onBack?: () => void;
}

type RecordingState = "idle" | "recording" | "stopped" | "uploading";
type InputMode = "audio" | "text";

function Recorder({
  question,
  jobDescription,
  userId,
  sessionId,
  questionOrder,
  onRecordingComplete,
  onSkip: _onSkip,
  onBack,
}: RecorderProps) {
  // State
  const [recordingState, setRecordingState] = useState<RecordingState>("idle");
  const [inputMode, setInputMode] = useState<InputMode>("audio");
  const [transcript, setTranscript] = useState("");
  const [interimTranscript, setInterimTranscript] = useState("");
  const [duration, setDuration] = useState(0);
  const [audioURL, setAudioURL] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [speechSupported, setSpeechSupported] = useState(true);
  const [localVideoStream, setLocalVideoStream] = useState<MediaStream | null>(
    null
  );
  const [videoMetrics, setVideoMetrics] = useState<VideoMetrics | null>(null);

  // Refs
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  // Check for speech recognition support
  useEffect(() => {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setSpeechSupported(false);
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (recognitionRef.current) recognitionRef.current.abort();
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
      }
      if (audioURL) URL.revokeObjectURL(audioURL);
    };
  }, [audioURL]);

  // Initialize speech recognition
  const initSpeechRecognition = useCallback(() => {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return null;

    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let finalTranscript = "";
      let interimResult = "";

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) {
          finalTranscript += result[0].transcript + " ";
        } else {
          interimResult += result[0].transcript;
        }
      }

      if (finalTranscript) {
        setTranscript((prev) => prev + finalTranscript);
      }
      setInterimTranscript(interimResult);
    };

    recognition.onerror = (event) => {
      console.error("[Speech Recognition Error]", event.error);
      if (event.error === "no-speech") {
        return;
      }
      setError(`Speech recognition error: ${event.error}`);
    };

    recognition.onend = () => {
      if (recordingState === "recording" && recognitionRef.current) {
        try {
          recognitionRef.current.start();
        } catch {
          // Ignore
        }
      }
    };

    return recognition;
  }, [recordingState]);

  // Start recording
  const startRecording = async () => {
    setError("");
    audioChunksRef.current = [];
    setTranscript("");
    setInterimTranscript("");
    setVideoMetrics(null);

    try {
      let stream: MediaStream;

      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
            channelCount: 1,
            sampleRate: 16000,
            sampleSize: 16,
          },
          video: {
            width: { ideal: 640 },
            height: { ideal: 480 },
            facingMode: "user",
          },
        });
        setLocalVideoStream(stream);
      } catch (videoErr) {
        console.warn(
          "[Media] Video not available, falling back to audio only:",
          videoErr
        );
        stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
            channelCount: 1,
            sampleRate: 16000,
            sampleSize: 16,
          },
        });
        setLocalVideoStream(null);
      }

      streamRef.current = stream;

      if (speechSupported) {
        const recognition = initSpeechRecognition();
        if (recognition) {
          recognitionRef.current = recognition;
          recognition.start();
        }
      }

      const mimeType = MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : MediaRecorder.isTypeSupported("audio/mp4")
          ? "audio/mp4"
          : "audio/ogg";

      const audioStream = new MediaStream(stream.getAudioTracks());
      const mediaRecorder = new MediaRecorder(audioStream, { mimeType });
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: mimeType });
        const url = URL.createObjectURL(audioBlob);
        setAudioURL(url);
        setRecordingState("stopped");
      };

      mediaRecorder.start(1000);
      setRecordingState("recording");
      setDuration(0);

      timerRef.current = setInterval(() => {
        setDuration((prev) => prev + 1);
      }, 1000);
    } catch (err) {
      console.error("Error accessing microphone:", err);
      setError("Could not access microphone. Please check permissions.");
    }
  };

  // Stop recording
  const stopRecording = () => {
    if (recordingState === "recording") {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }

      if (mediaRecorderRef.current) {
        mediaRecorderRef.current.stop();
      }

      if (timerRef.current) {
        clearInterval(timerRef.current);
      }

      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
      }

      setInterimTranscript("");
    }
  };

  // Re-record
  const resetRecording = () => {
    if (audioURL) {
      URL.revokeObjectURL(audioURL);
    }
    setAudioURL("");
    setDuration(0);
    setTranscript("");
    setInterimTranscript("");
    setRecordingState("idle");
    setError("");
    setVideoMetrics(null);
    setInputMode("audio");
    // Don't clear localVideoStream as we want to keep the camera preview text
  };

  // Submit recording
  const submitRecording = async () => {
    const finalTranscript = transcript.trim();

    if (!finalTranscript) {
      setError("No speech detected. Please record your answer again.");
      return;
    }

    setRecordingState("uploading");
    setIsLoading(true);
    setError("");
    const toastId = toast.loading("Analyzing your answer...", {
      description: "Our AI is generating personalized feedback.",
    });

    try {
      const response = await fetch("/api/v1/submit_answer", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          question_id: question.id,
          transcript: finalTranscript,
          duration_seconds: duration,
          job_description: jobDescription || undefined,
          user_id: userId,
          session_id: sessionId,
          question_order: questionOrder,
          domain: question.domain || "general",
          difficulty: question.difficulty || "medium",
        }),
      });

      if (!response.ok) {
        const errorData = await response
          .json()
          .catch(() => ({ detail: "Submission failed" }));
        throw new Error(errorData.detail || "Failed to analyze answer");
      }

      const feedback = await response.json();
      if (videoMetrics) {
        feedback.video_metrics = {
          eye_contact_percent: videoMetrics.eyeContactPercent,
          expression: videoMetrics.dominantExpression,
          movement_stability: videoMetrics.movementStability,
          visual_confidence: videoMetrics.overallConfidence,
        };
      }

      // Upload audio in background (don't await - fire and forget)
      if (audioChunksRef.current.length > 0) {
        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/webm" });
        uploadAudioInBackground(audioBlob, feedback.attempt_id);
      }

      onRecordingComplete(feedback);
      toast.dismiss(toastId);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Failed to analyze recording";
      setError(errorMessage);
      toast.error("Analysis failed", {
        id: toastId,
        description: errorMessage
      });
      setRecordingState("stopped");
    } finally {
      setIsLoading(false);
    }
  };

  // Background audio upload - runs after feedback is complete
  const uploadAudioInBackground = async (audioBlob: Blob, attemptId?: number) => {
    if (!attemptId) {
      console.log("No attempt ID, skipping audio upload");
      return;
    }

    try {
      const formData = new FormData();
      formData.append("audio", audioBlob, `${sessionId}_q${questionOrder}.webm`);
      formData.append("user_id", userId);
      formData.append("session_id", sessionId);
      formData.append("question_order", questionOrder.toString());
      formData.append("attempt_id", attemptId.toString());

      const response = await fetch("/api/v1/upload_attempt_audio", {
        method: "POST",
        body: formData,
      });

      if (response.ok) {
        console.log("Audio uploaded successfully for attempt", attemptId);
      } else {
        console.warn("Audio upload failed:", await response.text());
      }
    } catch (err) {
      console.warn("Background audio upload error:", err);
      // Don't throw - audio upload failure shouldn't affect user experience
    }
  };

  // Format duration
  const formatDuration = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, "0")}:${secs
      .toString()
      .padStart(2, "0")}`;
  };

  const fullTranscript = transcript + interimTranscript;
  const wordCount = transcript.split(/\s+/).filter((w) => w).length;

  // Speech Synthesis
  const speakQuestion = () => {
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel(); // Stop any current speech
      const utterance = new SpeechSynthesisUtterance(question.question);
      utterance.rate = 1.0;
      utterance.pitch = 1.0;
      utterance.volume = 1.0;
      window.speechSynthesis.speak(utterance);
    } else {
      toast.error("Text-to-speech not supported in this browser");
    }
  };

  useEffect(() => {
    // Stop speech when component unmounts
    return () => {
      if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  return (
    <div className="recorder-fullscreen">
      {/* Header Bar */}
      <div className="recorder-header">
        <div className="recorder-header-left">
          {onBack && recordingState === "idle" && (
            <button className="back-btn" onClick={onBack}>
              ← Back
            </button>
          )}
          <div className={`recording-indicator ${recordingState} rounded-full`}>
            <span className="indicator-dot"></span>
            <span className="indicator-text">
              {recordingState === "idle" && "Ready"}
              {recordingState === "recording" && "Recording"}
              {recordingState === "stopped" && "Stopped"}
              {recordingState === "uploading" && "Analyzing..."}
            </span>
          </div>
          <div className="duration-badge rounded-full">
            <span className="duration-icon">⏱</span>
            <span className="duration-time">{formatDuration(duration)}</span>
          </div>
        </div>
        <div className="recorder-header-center flex flex-col items-center justify-center gap-1">
          <div className="flex items-center gap-2">
            <span className="px-3 py-1 bg-stone-100 dark:bg-surface-800 text-stone-600 dark:text-surface-300 rounded-full text-xs font-bold uppercase tracking-wider border border-stone-200 dark:border-surface-700 shadow-sm">
              {question.category || question.domain || "General"}
            </span>
          </div>
          <h2 className="text-lg font-display font-bold text-stone-800 dark:text-white">
            Question {question.questionNumber || question.id}
            <span className="text-stone-400 dark:text-surface-500 font-normal ml-1">
              / {question.totalQuestions || "?"}
            </span>
          </h2>
        </div>
        <div className="recorder-header-right">
          {question.difficulty && (
            <span className={`difficulty-badge ${question.difficulty} rounded-full`}>
              {question.difficulty}
            </span>
          )}
        </div>
      </div>

      {/* Main Content - 3 Column Layout */}
      <div className="recorder-content">
        {/* Left Column - Video & Audio */}
        <div className="recorder-column recorder-col-video">
          <div className="column-header">
            <span className="column-icon">
              <Video className="w-5 h-5" />
            </span>
            <h3>Video Preview</h3>
          </div>
          <div className="column-body">
            {/* Video Preview */}
            <div className={`video-container rounded-2xl overflow-hidden shadow-lg ${recordingState === 'recording' ? 'ring-2 ring-red-500' : ''}`}>
              {(recordingState === "recording" ||
                recordingState === "stopped") &&
                localVideoStream ? (
                <VideoAnalyzer
                  videoStream={localVideoStream}
                  isAnalyzing={recordingState === "recording"}
                  showOverlayToUser={false}
                  onFinalMetrics={(metrics) => setVideoMetrics(metrics)}
                />
              ) : (
                <div className="video-placeholder bg-stone-100 dark:bg-surface-900">
                  <span className="placeholder-icon text-stone-300 dark:text-surface-600">
                    <Camera className="w-10 h-10" />
                  </span>
                  <p className="text-stone-400 dark:text-surface-500">Camera preview</p>
                </div>
              )}
            </div>


            {/* Video Metrics */}
            {videoMetrics && recordingState === "stopped" && (
              <div className="video-metrics-card">
                <h4>Visual Analysis</h4>
                <div className="metrics-grid">
                  <div className="metric-item">
                    <span className="metric-label">Eye Contact</span>
                    <span className="metric-value">
                      {videoMetrics.eyeContactPercent}%
                    </span>
                  </div>
                  <div className="metric-item">
                    <span className="metric-label">Expression</span>
                    <span className="metric-value">
                      {videoMetrics.dominantExpression}
                    </span>
                  </div>
                  <div className="metric-item">
                    <span className="metric-label">Stability</span>
                    <span className="metric-value">
                      {videoMetrics.movementStability}%
                    </span>
                  </div>
                  <div className="metric-item highlight">
                    <span className="metric-label">Confidence</span>
                    <span className="metric-value">
                      {videoMetrics.overallConfidence}/100
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* Audio Playback */}
            {audioURL && recordingState === "stopped" && (
              <div className="audio-playback-card">
                <h4>
                  <Headphones className="w-4 h-4 inline mr-2" />
                  Audio Recording
                </h4>
                <audio controls src={audioURL} className="audio-player" />
              </div>
            )}

            {/* Recording Controls */}
            <div className="recording-controls">
              {recordingState === "idle" && (
                <button
                  className="control-btn start-btn"
                  onClick={startRecording}
                >
                  <span className="btn-icon">
                    <Mic className="w-5 h-5" />
                  </span>
                  Start Recording
                </button>
              )}

              {recordingState === "recording" && (
                <button
                  className="control-btn stop-btn"
                  onClick={stopRecording}
                >
                  <span className="btn-icon">
                    <Square className="w-5 h-5" />
                  </span>
                  Stop Recording
                </button>
              )}

              {recordingState === "stopped" && (
                <div className="control-group flex flex-col gap-3">
                  {/* Primary Actions Grid */}
                  <div className="grid grid-cols-2 gap-3">
                    <button
                      className="control-btn submit-btn py-3 rounded-xl bg-gradient-to-r from-primary-600 to-secondary-600 hover:from-primary-700 hover:to-secondary-700 text-white font-bold shadow-lg shadow-primary-500/20 transition-all flex items-center justify-center gap-2"
                      onClick={submitRecording}
                      disabled={!transcript.trim() && !interimTranscript && inputMode === 'audio'}
                    >
                      <span className="btn-icon">
                        {isLoading ? <LoadingSpinner size="sm" className="text-white" /> : <Sparkles className="w-5 h-5" />}
                      </span>
                      {isLoading ? "Analyzing..." : "Submit Answer"}
                    </button>

                    <button
                      className="control-btn retry-btn py-3 rounded-xl bg-stone-100 dark:bg-surface-700 hover:bg-stone-200 dark:hover:bg-surface-600 text-stone-700 dark:text-surface-200 font-medium transition-all flex items-center justify-center gap-2"
                      onClick={resetRecording}
                    >
                      <RotateCcw className="w-4 h-4" />
                      Retry
                    </button>
                  </div>

                  {/* Text Input Toggle */}
                  {inputMode !== 'text' && (
                    <button
                      className="w-full py-3 rounded-xl border border-stone-200 dark:border-surface-600 text-stone-600 dark:text-surface-300 hover:bg-stone-50 dark:hover:bg-surface-800 text-sm font-bold transition-all flex items-center justify-center gap-2 shadow-sm hover:shadow-md"
                      onClick={() => {
                        setInputMode('text');
                        // If current transcript exists, keep it for editing
                      }}
                    >
                      <Keyboard className="w-4 h-4" />
                      Switch to Text Input / Edit Answer
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Middle Column - Question & Transcript */}
        <div className="recorder-column recorder-col-transcript">
          <div className="column-header">
            <span className="column-icon">
              <FileText className="w-5 h-5" />
            </span>
            <h3>Question & Transcript</h3>
          </div>
          <div className="column-body">
            {/* Question Display */}
            <div className="question-card">
              <div className="flex justify-between items-start mb-2">
                <h4>Interview Question</h4>
                <button
                  onClick={speakQuestion}
                  className="p-1.5 rounded-full hover:bg-stone-100 dark:hover:bg-surface-700 text-stone-500 dark:text-surface-400 hover:text-primary-500 dark:hover:text-primary-400 transition-colors"
                  title="Read Question Aloud"
                >
                  <Volume2 className="w-4 h-4" />
                </button>
              </div>
              <p className="question-text">{question.question}</p>
              {question.keywords && question.keywords.length > 0 && (
                <div className="keywords-row">
                  <span className="keywords-label">Key Topics:</span>
                  <div className="keywords-list">
                    {question.keywords.slice(0, 5).map((kw, idx) => (
                      <span key={idx} className="keyword-tag">
                        {kw}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Live Transcript */}
            <div className="transcript-card">
              <div className="transcript-header">
                <h4>
                  {recordingState === "recording" ? (
                    <>
                      <Circle className="w-3 h-3 inline mr-1 text-red-500 fill-red-500" />
                      Live Transcript
                    </>
                  ) : (
                    <>
                      <FileText className="w-4 h-4 inline mr-1" />
                      Your Answer
                    </>
                  )}
                </h4>
                {transcript && (
                  <span className="word-count">{wordCount} words</span>
                )}
              </div>
              <div
                className={`transcript-content ${recordingState === "recording" ? "live" : ""
                  }`}
              >
                {fullTranscript || (
                  <span className="transcript-placeholder">
                    {recordingState === "recording"
                      ? "Start speaking... Your words will appear here in real-time."
                      : recordingState === "idle"
                        ? inputMode === 'text'
                          ? "Type your answer below..."
                          : 'Click "Start Recording" or switch to text mode.'
                        : "No answer provided yet."}
                  </span>
                )}
                {recordingState === "recording" && interimTranscript && (
                  <span className="interim-text"> {interimTranscript}</span>
                )}
              </div>
            </div>

            {/* Error Display */}
            {error && (
              <div className="error-card">
                <span className="error-icon">
                  <AlertTriangle className="w-5 h-5" />
                </span>
                <p>{error}</p>
              </div>
            )}

            {/* Speech Support Warning */}
            {!speechSupported && inputMode !== 'text' && (
              <div className="warning-card">
                <span className="warning-icon">
                  <AlertTriangle className="w-5 h-5" />
                </span>
                <p>
                  Speech recognition not supported. Please use Chrome, Edge, or
                  Safari, or switch to text input mode below.
                </p>
              </div>
            )}



            {/* Text Input Logic */}
            {inputMode === "text" && (
              <div className="mt-4 space-y-3 animation-fade-in">
                <div className="p-4 bg-white dark:bg-surface-800 rounded-xl border border-stone-200 dark:border-surface-700 shadow-sm">
                  <div className="flex justify-between items-center mb-2">
                    <h4 className="text-sm font-semibold text-stone-700 dark:text-white flex items-center gap-2">
                      <Keyboard className="w-4 h-4 text-primary-500" />
                      Your Answer
                    </h4>
                    {recordingState === 'idle' && (
                      <button
                        onClick={() => setInputMode('audio')}
                        className="text-xs text-primary-500 hover:text-primary-600 underline"
                      >
                        Switch to Audio
                      </button>
                    )}
                  </div>
                  <textarea
                    value={transcript}
                    onChange={(e) => setTranscript(e.target.value)}
                    placeholder="Type your answer here..."
                    className="w-full h-48 p-3 rounded-lg bg-stone-50 dark:bg-surface-900 border border-stone-200 dark:border-surface-600 text-stone-700 dark:text-surface-200 text-sm resize-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500 transition-all"
                  />
                  <div className="flex justify-end mt-2">
                    <span className="text-xs text-stone-500 dark:text-surface-400">
                      {transcript.split(/\s+/).filter(w => w).length} words
                    </span>
                  </div>
                </div>

                {/* Submit Button for Text Mode (if not handling in main controls) */}
                {recordingState === 'idle' && (
                  <button
                    className="w-full py-3 rounded-xl bg-primary-600 hover:bg-primary-700 text-white font-bold shadow-lg shadow-primary-500/20 transition-all flex items-center justify-center gap-2"
                    onClick={submitRecording}
                    disabled={!transcript.trim() || isLoading}
                  >
                    {isLoading ? <LoadingSpinner size="sm" className="text-white" /> : <Sparkles className="w-5 h-5" />}
                    {isLoading ? "Analyzing..." : "Submit Text Answer"}
                  </button>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Right Column - Tips & Guidelines */}
        <div className="recorder-column recorder-col-tips">
          <div className="column-header">
            <span className="column-icon">
              <Lightbulb className="w-5 h-5" />
            </span>
            <h3>Tips & Guidelines</h3>
          </div>
          <div className="column-body">
            {/* STAR Method */}
            <div className="tip-card">
              <h4>
                <Star className="w-4 h-4 inline mr-2 text-yellow-500" />
                Use the STAR Method
              </h4>
              <style>{`
  /* Hide scrollbars for all recorder columns and scrollable areas */
  .recorder-column .column-body,
  .transcript-content,
  .keywords-list,
  .video-container,
  .space-y-1\\.5 {
    scrollbar-width: none; /* Firefox */
    -ms-overflow-style: none; /* IE and Edge */
  }
  
  .recorder-column .column-body::-webkit-scrollbar,
  .transcript-content::-webkit-scrollbar,
  .keywords-list::-webkit-scrollbar,
  .video-container::-webkit-scrollbar,
  .space-y-1\\.5::-webkit-scrollbar {
    display: none;
  }
`}</style>
              <ul className="tip-list">
                <li>
                  <strong>S</strong>ituation - Set the scene
                </li>
                <li>
                  <strong>T</strong>ask - Describe your responsibility
                </li>
                <li>
                  <strong>A</strong>ction - Explain what you did
                </li>
                <li>
                  <strong>R</strong>esult - Share the outcome
                </li>
              </ul>
            </div>

            {/* Speaking Tips */}
            <div className="tip-card">
              <h4>
                <Mic className="w-4 h-4 inline mr-2 text-blue-500" />
                Speaking Tips
              </h4>
              <ul className="tip-list">
                <li>Speak clearly at 130-160 WPM</li>
                <li>Pause between thoughts</li>
                <li>Avoid filler words (um, uh, like)</li>
                <li>Use specific examples & numbers</li>
              </ul>
            </div>

            {/* Body Language */}
            <div className="tip-card">
              <h4>
                <Eye className="w-4 h-4 inline mr-2 text-green-500" />
                Body Language
              </h4>
              <ul className="tip-list">
                <li>Maintain eye contact with camera</li>
                <li>Keep good posture</li>
                <li>Use natural hand gestures</li>
                <li>Smile when appropriate</li>
              </ul>
            </div>

            {/* Time Guide */}
            <div className="tip-card time-guide">
              <h4>
                <Clock className="w-4 h-4 inline mr-2 text-purple-500" />
                Ideal Answer Length
              </h4>
              <div className="time-ranges">
                <div className="time-range">
                  <span className="range-label">Quick Answer</span>
                  <span className="range-value">1-2 min</span>
                </div>
                <div className="time-range highlight">
                  <span className="range-label">Detailed Answer</span>
                  <span className="range-value">2-3 min</span>
                </div>
                <div className="time-range">
                  <span className="range-label">Maximum</span>
                  <span className="range-value">4 min</span>
                </div>
              </div>
            </div>

            {/* Checklist */}
            <div className="tip-card checklist">
              <h4>
                <CheckCircle2 className="w-4 h-4 inline mr-2 text-green-500" />
                Before Submitting
              </h4>
              <ul className="checklist-list">
                <li className={transcript.length > 50 ? "checked" : ""}>
                  Answer is substantial
                </li>
                <li className={duration >= 30 ? "checked" : ""}>
                  At least 30 seconds
                </li>
                <li className={wordCount >= 50 ? "checked" : ""}>
                  50+ words spoken
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Recorder;
