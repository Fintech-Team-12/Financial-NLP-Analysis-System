import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import { Send, Bot, User } from 'lucide-react';
import './ChatPage.css';

const API_BASE_URL = 'http://localhost:8000/api';

const ChatPage = ({ currentChatId, setCurrentChatId }) => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [chatTitle, setChatTitle] = useState('New Chatting');

  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  useEffect(() => {
    const fetchMessages = async () => {
      if (!currentChatId) {
        setChatTitle('New Chatting');
        setMessages([
          { id: 'welcome', role: 'assistant', content: '안녕하세요! 감사보고서 분석 어시스턴트입니다. 새로운 대화를 시작했습니다. 무엇을 도와드릴까요?' }
        ]);
        return;
      }

      const token = localStorage.getItem('token');
      try {
        const res = await axios.get(`${API_BASE_URL}/chats/${currentChatId}/messages`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        setMessages(res.data.messages || []);
        setChatTitle(res.data.title || 'New Chatting');
      } catch (error) {
        console.error('Failed to load messages', error);
      }
    };

    fetchMessages();
  }, [currentChatId]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const token = localStorage.getItem('token');
    const userMessageContent = input.trim();
    setInput('');
    setIsLoading(true);

    setMessages(prev => [...prev, { id: 'optimistic', role: 'user', content: userMessageContent }]);

    try {
      const payload = {
        question: userMessageContent,
        year: 2024
      };

      if (currentChatId) {
        payload.chat_id = currentChatId;
      }

      const response = await axios.post(`${API_BASE_URL}/chat`, payload, {
        headers: { Authorization: `Bearer ${token}` },
        timeout: 60000
      });

      if (!currentChatId && response.data.chat_id) {
        setCurrentChatId(response.data.chat_id);
      } else {
        setMessages(prev => {
          return [...prev.filter(m => m.id !== 'optimistic'),
          { id: Date.now(), role: 'user', content: userMessageContent },
          { id: Date.now() + 1, role: 'assistant', content: response.data.answer }
          ];
        });
      }
    } catch (error) {
      console.error('API Request Failed:', error);
      setMessages(prev => [
        ...prev.filter(m => m.id !== 'optimistic'),
        { id: Date.now(), role: 'user', content: userMessageContent },
        { id: Date.now() + 1, role: 'assistant', content: `Error: 백엔드 통신 실패. ${error.message}`, isError: true }
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.nativeEvent.isComposing) return;
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="chat-page">
      <header className="chat-header glass">
        <div className="header-title">
          <h2>{chatTitle}</h2>
          <span className="badge">JWT Active</span>
        </div>
      </header>

      <div className="messages-container">
        {messages.map((msg) => (
          <div key={msg.id} className={`message-wrapper ${msg.role}`}>
            <div className="message-avatar">
              {msg.role === 'assistant' ? <Bot size={20} /> : <User size={20} />}
            </div>
            <div className={`message-bubble ${msg.isError ? 'error' : ''}`}>
              {msg.content}
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="message-wrapper assistant">
            <div className="message-avatar">
              <Bot size={20} />
            </div>
            <div className="message-bubble typing-indicator">
              <span></span><span></span><span></span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="input-container glass">
        <div className="input-wrapper">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="질문을 입력하세요..."
            rows={1}
            autoFocus
          />

          <button
            className={`send-btn ${input.trim() ? 'active' : ''}`}
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
          >
            <Send size={18} />
          </button>
        </div>
      </div>
    </div>
  );
};

export default ChatPage;
