import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { MessageSquarePlus, LogOut, PanelLeftClose, PanelLeft, Settings, MessageSquare, Database, Pencil, Trash2, Check, X } from 'lucide-react';
import FileUploader from './FileUploader';
import './Layout.css';

const API_BASE_URL = 'http://localhost:8000/api';

const Layout = ({ children, user, onLogout, currentChatId, setCurrentChatId }) => {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [history, setHistory] = useState([]);
  const [isUploaderOpen, setIsUploaderOpen] = useState(false);
  const [editingChatId, setEditingChatId] = useState(null);
  const [editTitle, setEditTitle] = useState('');

  const fetchChats = async () => {
    const token = localStorage.getItem('token');
    if (!token) return;

    try {
      const res = await axios.get(`${API_BASE_URL}/chats`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setHistory(res.data);
    } catch (err) {
      console.error("Failed to fetch chats:", err);
    }
  };

  useEffect(() => {
    fetchChats();
  }, [currentChatId]);

  const handleNewChat = () => {
    setCurrentChatId(null);
  };

  const handleSelectChat = (id) => {
    setCurrentChatId(id);
  };

  const handleRenameClick = (chat) => {
    setEditingChatId(chat.id);
    setEditTitle(chat.title);
  };

  const submitRename = async (id) => {
    if (!editTitle.trim()) return;
    const token = localStorage.getItem('token');
    try {
      await axios.put(`${API_BASE_URL}/chats/${id}`, { title: editTitle }, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setEditingChatId(null);
      fetchChats();
    } catch (err) {
      console.error(err);
    }
  };

  const handleDeleteChat = async (id) => {
    if (!window.confirm("정말 이 채팅방을 삭제하시겠습니까?")) return;
    const token = localStorage.getItem('token');
    try {
      await axios.delete(`${API_BASE_URL}/chats/${id}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (currentChatId === id) setCurrentChatId(null);
      fetchChats();
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className={`layout-container ${sidebarOpen ? 'sidebar-open' : 'sidebar-closed'}`}>
      <aside className="sidebar glass">
        <div className="sidebar-header">
          <div className="header-top">
            <button className="new-chat-btn" onClick={handleNewChat}>
              <MessageSquarePlus size={20} />
              <span>New Chat</span>
            </button>
            <button className="collapse-btn" onClick={() => setSidebarOpen(false)}>
              <PanelLeftClose size={20} />
            </button>
          </div>
          <button className="sidebar-upload-btn" onClick={() => setIsUploaderOpen(true)}>
            <Database size={18} />
            <span>지식 베이스 업로드 (RAG)</span>
          </button>
        </div>

        <div className="sidebar-content">
          <p className="section-title">Recent Chats</p>
          <ul className="chat-history">
            {history.map(chat => (
              <li key={chat.id} className={`chat-item-wrapper ${currentChatId === chat.id ? 'active' : ''}`}>
                {editingChatId === chat.id ? (
                  <div className="chat-edit-wrapper">
                    <input
                      type="text"
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') submitRename(chat.id);
                        if (e.key === 'Escape') setEditingChatId(null);
                      }}
                      autoFocus
                      className="chat-edit-input"
                    />
                    <button onClick={() => submitRename(chat.id)} className="chat-action-btn"><Check size={14} /></button>
                    <button onClick={() => setEditingChatId(null)} className="chat-action-btn"><X size={14} /></button>
                  </div>
                ) : (
                  <>
                    <button
                      className="history-btn"
                      onClick={() => handleSelectChat(chat.id)}
                    >
                      <MessageSquare size={16} />
                      <span className="chat-truncate">{chat.title}</span>
                    </button>
                    <div className="chat-hover-actions">
                      <button onClick={(e) => { e.stopPropagation(); handleRenameClick(chat); }} className="chat-action-btn"><Pencil size={14} /></button>
                      <button onClick={(e) => { e.stopPropagation(); handleDeleteChat(chat.id); }} className="chat-action-btn"><Trash2 size={14} /></button>
                    </div>
                  </>
                )}
              </li>
            ))}
          </ul>
        </div>

        <div className="sidebar-footer">
          <button className="profile-btn">
            <img src={user?.avatar || `https://ui-avatars.com/api/?name=${user?.name || "User"}&background=0D8ABC&color=fff`} alt="Avatar" className="avatar" />
            <span className="user-name">{user?.name}</span>
          </button>
          <button className="logout-btn" onClick={onLogout} title="Logout">
            <LogOut size={18} />
          </button>
        </div>
      </aside>

      <main className="main-content">
        {!sidebarOpen && (
          <button className="open-sidebar-btn" onClick={() => setSidebarOpen(true)}>
            <PanelLeft size={24} />
          </button>
        )}
        {children}
      </main>

      {isUploaderOpen && (
        <FileUploader onClose={() => setIsUploaderOpen(false)} />
      )}
    </div>
  );
};

export default Layout;
