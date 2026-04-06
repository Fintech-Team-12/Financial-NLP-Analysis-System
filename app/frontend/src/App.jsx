import React, { useState, useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import ChatPage from './pages/ChatPage';
import Layout from './components/Layout';
import { jwtDecode } from "jwt-decode";

function App() {
  const [user, setUser] = useState(null);
  const [currentChatId, setCurrentChatId] = useState(null);

  useEffect(() => {
    const token = localStorage.getItem('token');
    const savedUser = localStorage.getItem('user');
    
    if (token && savedUser) {
      try {
        const decoded = jwtDecode(token);
        if (decoded.exp * 1000 > Date.now() || !decoded.exp) {
          setUser(JSON.parse(savedUser));
        } else {
          handleLogout();
        }
      } catch (err) {
        handleLogout();
      }
    }
  }, []);

  const handleLogin = (userData) => {
    setUser(userData);
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    setUser(null);
    setCurrentChatId(null);
  };

  return (
    <Routes>
      <Route 
        path="/login" 
        element={!user ? <Login onLogin={handleLogin} /> : <Navigate to="/" />} 
      />
      <Route 
        path="/" 
        element={
          user ? (
            <Layout 
              user={user} 
              onLogout={handleLogout} 
              currentChatId={currentChatId}
              setCurrentChatId={setCurrentChatId}
            >
              <ChatPage currentChatId={currentChatId} setCurrentChatId={setCurrentChatId} />
            </Layout>
          ) : (
            <Navigate to="/login" />
          )
        } 
      />
    </Routes>
  );
}

export default App;
