import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { MessageSquarePlus, LogOut, PanelLeftClose, PanelLeft, Settings, MessageSquare, Database } from 'lucide-react';
import FileUploader from './FileUploader';
import './Layout.css';

const API_BASE_URL = 'http://localhost:8000/api';

const Layout = ({ children, user, onLogout, currentChatId, setCurrentChatId }) => {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [history, setHistory] = useState([]);
  const [isUploaderOpen, setIsUploaderOpen] = useState(false);

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
              <li key={chat.id}>
                <button 
                  className={`history-btn ${currentChatId === chat.id ? 'active' : ''}`}
                  onClick={() => handleSelectChat(chat.id)}
                >
                  <MessageSquare size={16} />
                  <span>{chat.title}</span>
                </button>
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
