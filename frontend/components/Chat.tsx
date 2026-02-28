'use client';

import { useState, useRef, useEffect } from 'react';
import { chat as chatAPI, Viewpoint } from '@/lib/api';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface Props {
  loading: boolean;
  setLoading: (loading: boolean) => void;
  onResults: (results: Viewpoint[]) => void;
}

export default function Chat({ loading, setLoading, onResults }: Props) {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content:
        'Welcome to smallworld. Tell me what kind of landscape shot you\'re looking for — describe the location, mood, and style. I\'ll find the optimal camera angles for you.',
    },
  ]);
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    const msg = input.trim();
    if (!msg || loading) return;

    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: msg }]);
    setLoading(true);

    try {
      const res = await chatAPI(msg);

      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: res.response },
      ]);

      if (res.results && res.results.length > 0) {
        onResults(res.results);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: 'Something went wrong connecting to the backend. Make sure the FastAPI server is running on port 8000.',
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="chat-panel">
      <div className="chat-messages">
        {messages.map((msg, i) => (
          <div key={i} className={`chat-message ${msg.role}`}>
            {msg.content}
          </div>
        ))}
        {loading && (
          <div className="loading">
            <div className="loading-dot" />
            <div className="loading-dot" />
            <div className="loading-dot" />
            Analyzing terrain...
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>
      <div className="chat-input-area">
        <input
          className="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Describe the shot you want..."
          disabled={loading}
        />
        <button
          className="chat-send"
          onClick={handleSend}
          disabled={loading || !input.trim()}
        >
          Send
        </button>
      </div>
    </div>
  );
}
