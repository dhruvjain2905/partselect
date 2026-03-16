import React, { useState, useCallback } from "react";
import "./App.css";
import Sidebar from "./components/Sidebar";
import ChatWindow from "./components/ChatWindow";
import { createSessionId } from "./api/api";

// Load saved chats from localStorage
function loadChats() {
  try {
    const raw = localStorage.getItem("ps_chats");
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveChats(chats) {
  localStorage.setItem("ps_chats", JSON.stringify(chats));
}

function App() {
  // Always start with a fresh chat on load
  const [activeId, setActiveId] = useState(() => createSessionId());
  const [chats, setChats] = useState(loadChats);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Save a chat snapshot (called by ChatWindow after each message)
  const onChatUpdate = useCallback(
    (id, title, messages, context) => {
      setChats((prev) => {
        const existing = prev.findIndex((c) => c.id === id);
        const updated = {
          id,
          title,
          messages,
          context,
          updatedAt: Date.now(),
        };
        let next;
        if (existing >= 0) {
          next = [...prev];
          next[existing] = updated;
        } else {
          next = [updated, ...prev];
        }
        // Keep only last 20 chats
        next = next.slice(0, 20);
        saveChats(next);
        return next;
      });
    },
    []
  );

  const handleNewChat = () => {
    setActiveId(createSessionId());
    setSidebarOpen(false);
  };

  const handleSelectChat = (id) => {
    setActiveId(id);
    setSidebarOpen(false);
  };

  const handleDeleteChat = (id) => {
    setChats((prev) => {
      const next = prev.filter((c) => c.id !== id);
      saveChats(next);
      return next;
    });
    if (id === activeId) {
      setActiveId(createSessionId());
    }
  };

  // Find the saved chat data if loading an existing one
  const savedChat = chats.find((c) => c.id === activeId);

  return (
    <div className="app">
      <header className="header">
        <div className="header-left">
          <button
            className="sidebar-toggle"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            aria-label="Toggle sidebar"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 12h18M3 6h18M3 18h18" strokeLinecap="round"/>
            </svg>
          </button>
          <div className="header-logo">
            <svg width="28" height="28" viewBox="0 0 32 32" fill="none">
              <path d="M16 2L2 14H6V28H26V14H30L16 2Z" fill="#E67E22"/>
              <text x="16" y="23" textAnchor="middle" fill="white" fontSize="14" fontWeight="700" fontFamily="Inter, sans-serif">P</text>
            </svg>
            <span className="header-brand">PartSelect</span>
          </div>
          <span className="header-divider" />
          <span className="header-tagline">Parts Assistant</span>
        </div>
        <div className="header-right">
          <button className="new-chat-btn" onClick={handleNewChat}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 5v14M5 12h14" strokeLinecap="round"/>
            </svg>
            New Chat
          </button>
          <div className="header-contact">
            <div className="header-phone">1-888-982-3893</div>
            <div className="header-hours">Mon-Sat 8am-8pm EST</div>
          </div>
        </div>
      </header>

      <Sidebar
        chats={chats}
        activeId={activeId}
        isOpen={sidebarOpen}
        onSelect={handleSelectChat}
        onDelete={handleDeleteChat}
        onNewChat={handleNewChat}
        onClose={() => setSidebarOpen(false)}
      />

      <ChatWindow
        key={activeId}
        chatId={activeId}
        savedChat={savedChat}
        onChatUpdate={onChatUpdate}
      />
    </div>
  );
}

export default App;
