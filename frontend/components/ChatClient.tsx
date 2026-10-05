"use client";

import {
  Bot,
  ExternalLink,
  FileText,
  Loader2,
  Search,
  Send,
  Sparkles,
  User
} from "lucide-react";
import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { ChatResponse, RetrievalResult } from "@/lib/types";

type Message = {
  role: "user" | "assistant";
  text: string;
  confidence?: string;
};

const starterSources: RetrievalResult[] = [];

const suggestedPrompts = [
  "What mass spectrometry instruments do you have?",
  "Which instrument should I use for coffee?",
  "How do I request DCIF training?"
];

export function ChatClient() {
  const formRef = useRef<HTMLFormElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sources, setSources] = useState<RetrievalResult[]>(starterSources);

  const sourceCount = useMemo(() => sources.length, [sources]);
  const canSubmit = input.trim().length > 0 && !loading;

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, loading]);

  async function sendMessage(message: string) {
    if (!message || loading) return;

    setInput("");
    setLoading(true);
    setMessages((current) => [...current, { role: "user", text: message }]);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, top_k: 5 })
      });
      if (!response.ok) throw new Error("Request failed");
      const payload = (await response.json()) as ChatResponse;
      setSources(payload.retrieved);
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          text: payload.answer.answer,
          confidence: payload.answer.confidence
        }
      ]);
    } catch {
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          text: "I could not get an answer right now. Check that the DCIF assistant service is running and try again."
        }
      ]);
    } finally {
      setLoading(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await sendMessage(input.trim());
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) {
      return;
    }
    event.preventDefault();
    formRef.current?.requestSubmit();
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand">
            <div className="brand-mark">MIT</div>
            <div>
              <div className="brand-title">DCIF Assistant</div>
              <div className="brand-subtitle">MIT Department of Chemistry Instrumentation Facility</div>
            </div>
          </div>
          <div className="status-pill">
            {loading ? <Loader2 size={15} /> : <Sparkles size={15} />}
            {loading ? "Searching" : `${sourceCount} sources`}
          </div>
        </div>
      </header>

      <section className="workspace">
        <div className="chat-panel">
          <div className="message-list">
            {messages.length === 0 ? (
              <section className="empty-state">
                <div className="empty-icon">
                  <Search size={22} />
                </div>
                <h1>Ask DCIF</h1>
                <p>
                  Search instruments, guides, training details, fees, and facility information from the
                  DCIF source collection.
                </p>
                <div className="prompt-grid">
                  {suggestedPrompts.map((prompt) => (
                    <button
                      className="prompt-chip"
                      key={prompt}
                      onClick={() => sendMessage(prompt)}
                      type="button"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </section>
            ) : null}

            {messages.map((message, index) => (
              <article className={`message-row ${message.role}`} key={`${message.role}-${index}`}>
                <div className="avatar" aria-hidden="true">
                  {message.role === "assistant" ? <Bot size={17} /> : <User size={17} />}
                </div>
                <div className="message-stack">
                  <div className="message-author">
                    {message.role === "assistant" ? "DCIF Assistant" : "You"}
                  </div>
                  <div className="message">
                    <div className="markdown-content">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.text}</ReactMarkdown>
                    </div>
                  </div>
                  {message.role === "assistant" && message.confidence ? (
                    <div className="message-meta">
                      <span className={`confidence ${message.confidence}`}>
                        {message.confidence} confidence
                      </span>
                    </div>
                  ) : null}
                </div>
              </article>
            ))}
            {loading ? (
              <article className="message-row assistant" aria-live="polite">
                <div className="avatar" aria-hidden="true">
                  <Bot size={17} />
                </div>
                <div className="message-stack">
                  <div className="message-author">DCIF Assistant</div>
                  <div className="message pending">
                    <Loader2 size={16} />
                    <span>Retrieving sources and drafting an answer</span>
                  </div>
                </div>
              </article>
            ) : null}
            <div ref={messagesEndRef} />
          </div>

          <form className="composer" onSubmit={submit} ref={formRef}>
            <div className="composer-box">
              <textarea
                aria-label="Ask a DCIF question"
                placeholder="Ask about instruments, training, scheduling, or facility policies"
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={handleComposerKeyDown}
              />
              <button className="icon-button" type="submit" disabled={!canSubmit} title="Send">
                {loading ? <Loader2 size={20} /> : <Send size={20} />}
              </button>
            </div>
          </form>
        </div>

        <aside className="source-panel">
          <div className="source-heading">
            <span>Sources</span>
            <span>{sourceCount}</span>
          </div>
          <div className="source-list">
            {sources.length === 0 ? (
              <div className="source-empty">
                <FileText size={18} />
                <span>No sources yet</span>
              </div>
            ) : null}
            {sources.map((source) => (
              <a
                className="source-card"
                href={source.source_url}
                key={source.chunk_id}
                target="_blank"
                rel="noreferrer"
              >
                <div className="source-card-top">
                  <span className="source-rank">{source.rank}</span>
                  <ExternalLink size={14} />
                </div>
                <div className="source-title">{source.source_title}</div>
                <div className="source-section">
                  {source.section_heading}
                  {source.page ? `, page ${source.page}` : ""}
                </div>
                <div className="source-text">{source.text.slice(0, 360)}</div>
              </a>
            ))}
          </div>
        </aside>
      </section>
    </main>
  );
}
