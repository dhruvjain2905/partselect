import React, { useState, useEffect, useRef, useCallback } from "react";
import "./ChatWindow.css";
import { getAIMessage } from "../api/api";
import { marked } from "marked";
import ProductCardList from "./ProductCard";

const WELCOME = {
  role: "assistant",
  content:
    "Welcome to **PartSelect**! I'm your appliance parts assistant for **Refrigerators** and **Dishwashers**.\n\nI can help you:\n- Find the right parts based on symptoms\n- Check part compatibility with your model\n- Get pricing, stock info, and installation guidance\n- Look up repair stories and expert Q&A\n\nWhat can I help you with today?",
  products: [],
};

const QUICK_PROMPTS = [
  { label: "Dishwasher not draining", icon: "\uD83E\uDEBD" },
  { label: "Ice maker stopped working", icon: "\u2744\uFE0F" },
  { label: "Parts for model WDT750SAHZ0", icon: "\uD83D\uDD0D" },
];

const LOADING_MESSAGES = [
  "Searching parts database",
  "Finding compatible parts",
  "Checking repair guides",
  "Looking up expert Q&A",
  "Preparing your answer",
];

function ChatWindow({ chatId, savedChat, onChatUpdate }) {
  const [messages, setMessages] = useState(
    savedChat ? savedChat.messages : [WELCOME]
  );
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [loadingMsg, setLoadingMsg] = useState(LOADING_MESSAGES[0]);
  const [context, setContext] = useState(savedChat?.context || {});

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const loadingIdx = useRef(0);

  // Cycle loading messages
  useEffect(() => {
    if (!isLoading) return;
    loadingIdx.current = 0;
    setLoadingMsg(LOADING_MESSAGES[0]);
    const interval = setInterval(() => {
      loadingIdx.current = (loadingIdx.current + 1) % LOADING_MESSAGES.length;
      setLoadingMsg(LOADING_MESSAGES[loadingIdx.current]);
    }, 2500);
    return () => clearInterval(interval);
  }, [isLoading]);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading, scrollToBottom]);

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Derive a chat title from first user message
  const getTitle = (msgs) => {
    const first = msgs.find((m) => m.role === "user");
    if (!first) return "New conversation";
    return first.content.length > 50
      ? first.content.slice(0, 50) + "..."
      : first.content;
  };

  const handleSend = async (text) => {
    const msg = (text || input).trim();
    if (!msg || isLoading) return;

    const userMsg = { role: "user", content: msg };
    const updatedMessages = [...messages, userMsg];
    setMessages(updatedMessages);
    setInput("");
    setIsLoading(true);

    const sendTime = Date.now();
    const response = await getAIMessage(msg, chatId);
    const elapsed = ((Date.now() - sendTime) / 1000).toFixed(1);
    response._responseTime = elapsed;

    const finalMessages = [...updatedMessages, response];
    setMessages(finalMessages);

    const newContext = response.context || context;
    if (response.context) setContext(newContext);

    setIsLoading(false);
    inputRef.current?.focus();

    // Save to parent for sidebar
    onChatUpdate(chatId, getTitle(finalMessages), finalMessages, newContext);
  };

  const hasContext = context.model_number || context.appliance_type;

  return (
    <div className="chat-layout">
      {/* Context bar */}
      {hasContext && (
        <div className="context-bar">
          <div className="context-tags">
            {context.appliance_type && (
              <span className="ctx-tag">
                {context.appliance_type === "dishwasher" ? "\uD83E\uDEBD" : "\u2744\uFE0F"}{" "}
                {context.appliance_type}
              </span>
            )}
            {context.brand && <span className="ctx-tag">{context.brand}</span>}
            {context.model_number && (
              <span className="ctx-tag ctx-model">
                Model: {context.model_number}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Messages */}
      <div className={`messages-area ${hasContext ? "has-context" : ""}`}>
        <div className="messages-inner">
          {messages.map((m, i) => (
            <div key={i} className={`msg-row ${m.role}`}>
              {m.role === "assistant" && (
                <div className="msg-avatar">
                  <svg width="16" height="16" viewBox="0 0 32 32" fill="none">
                    <path d="M16 2L2 14H6V28H26V14H30L16 2Z" fill="white" />
                  </svg>
                </div>
              )}
              <div className="msg-body">
                {m.content && (
                  <div
                    className={`msg-bubble ${m.role}`}
                    dangerouslySetInnerHTML={{
                      __html: marked(m.content, { breaks: true }),
                    }}
                  />
                )}
                {m.products && m.products.length > 0 && (
                  <ProductCardList products={m.products} />
                )}
                {m.role === "assistant" && m._responseTime && (
                  <div className="msg-meta">Response time: {m._responseTime}s</div>
                )}
              </div>
            </div>
          ))}

          {/* Loading */}
          {isLoading && (
            <div className="msg-row assistant">
              <div className="msg-avatar">
                <svg width="16" height="16" viewBox="0 0 32 32" fill="none">
                  <path d="M16 2L2 14H6V28H26V14H30L16 2Z" fill="white" />
                </svg>
              </div>
              <div className="msg-body">
                <div className="msg-bubble assistant loading-bubble">
                  <div className="loading-content">
                    <div className="loading-dots">
                      <span />
                      <span />
                      <span />
                    </div>
                    <span className="loading-text">{loadingMsg}</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Quick prompts */}
          {messages.length === 1 && !isLoading && (
            <div className="quick-prompts">
              {QUICK_PROMPTS.map((p, i) => (
                <button
                  key={i}
                  className="quick-btn"
                  onClick={() => handleSend(p.label)}
                >
                  <span className="quick-icon">{p.icon}</span>
                  {p.label}
                </button>
              ))}
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input */}
      <div className="input-area">
        <div className="input-box">
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about refrigerator or dishwasher parts..."
            disabled={isLoading}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
          />
          <button
            className="send-btn"
            onClick={() => handleSend()}
            disabled={isLoading || !input.trim()}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </button>
        </div>
        <div className="input-disclaimer">
          PartSelect Assistant may make mistakes. Please verify part compatibility on{" "}
          <a href="https://www.partselect.com" target="_blank" rel="noopener noreferrer">
            partselect.com
          </a>
          .
        </div>
      </div>
    </div>
  );
}

export default ChatWindow;
