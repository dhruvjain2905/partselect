import React from "react";
import "./Sidebar.css";

function Sidebar({ chats, activeId, isOpen, onSelect, onDelete, onNewChat, onClose }) {
  return (
    <>
      {/* Overlay */}
      {isOpen && <div className="sidebar-overlay" onClick={onClose} />}

      <div className={`sidebar ${isOpen ? "open" : ""}`}>
        <div className="sidebar-header">
          <span className="sidebar-title">Conversations</span>
          <button className="sidebar-new" onClick={onNewChat}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 5v14M5 12h14" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        <div className="sidebar-list">
          {chats.length === 0 && (
            <div className="sidebar-empty">No previous conversations</div>
          )}
          {chats.map((chat) => (
            <div
              key={chat.id}
              className={`sidebar-item ${chat.id === activeId ? "active" : ""}`}
              onClick={() => onSelect(chat.id)}
            >
              <div className="sidebar-item-content">
                <div className="sidebar-item-title">{chat.title || "New conversation"}</div>
                <div className="sidebar-item-meta">
                  {chat.context?.appliance_type && (
                    <span>{chat.context.appliance_type === "dishwasher" ? "\uD83E\uDEBD" : "\u2744\uFE0F"}</span>
                  )}
                  {chat.context?.model_number && (
                    <span className="sidebar-model">{chat.context.model_number}</span>
                  )}
                </div>
              </div>
              <button
                className="sidebar-item-delete"
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(chat.id);
                }}
                aria-label="Delete conversation"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M18 6L6 18M6 6l12 12" strokeLinecap="round" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

export default Sidebar;
