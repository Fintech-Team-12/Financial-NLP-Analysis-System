import React, { useState } from 'react';
import axios from 'axios';
import { GoogleLogin } from '@react-oauth/google';
import './Login.css';

const API_BASE_URL = 'http://localhost:8000/api';

const Login = ({ onLogin }) => {
  const [errorMsg, setErrorMsg] = useState("");

  const handleGoogleSuccess = async (credentialResponse) => {
    try {
      const { credential } = credentialResponse;

      const res = await axios.post(`${API_BASE_URL}/auth/google`, {
        google_token: credential
      });

      const { access_token, user_info } = res.data;

      localStorage.setItem('token', access_token);
      localStorage.setItem('user', JSON.stringify(user_info));

      onLogin(user_info);
    } catch (error) {
      console.error("Login failed", error);
      setErrorMsg("로그인 중 서버와 통신을 실패했습니다.");
    }
  };

  const handleGoogleError = () => {
    setErrorMsg("구글 로그인에 실패했습니다. 올바른 계정을 사용해 주세요.");
  };

  return (
    <div className="login-container">
      <div className="login-card glass animate-slide-up">
        <div className="login-header">
          <div className="logo-icon">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 3v18h18" />
              <path d="m19 9-5 5-4-4-3 3" />
            </svg>
          </div>
          <h1>Finance QA</h1>
          <p>Sign in to access your financial insights</p>
        </div>

        {errorMsg && <p style={{ color: '#ef4444', marginBottom: '1rem', fontSize: '0.9rem', textAlign: 'center' }}>{errorMsg}</p>}

        <div className="google-auth-wrapper">
          <GoogleLogin
            onSuccess={handleGoogleSuccess}
            onError={handleGoogleError}
            theme="filled_blue"
            size="large"
            width="100%"
          />
        </div>

        <div className="login-footer">
          <p>By continuing, you agree to our Terms of Service</p>
        </div>
      </div>
    </div>
  );
};

export default Login;
