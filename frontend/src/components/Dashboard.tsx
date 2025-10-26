import React from 'react';
import './Dashboard.css';
import AttentionScore from './AttentionScore';

type AgentMode = 'goggins' | 'health';

interface DashboardProps {
  attentionScore: number;
  onDecreaseAttention: () => void;
  onGetVoiceNudge: () => void;
  onGetNotificationNudge: () => void;
  loading: boolean;
  nudgeExecuted: boolean;
  notificationSent: boolean;
  notificationPermission: NotificationPermission;
  onRequestNotificationPermission: () => void;
  agentMode: AgentMode;
  onAgentModeChange: (mode: AgentMode) => void;
  lastNudgeType: 'voice' | 'health' | null;
  pomodoroTimer: React.ReactNode;
}

const Dashboard: React.FC<DashboardProps> = ({
  attentionScore,
  onDecreaseAttention,
  onGetVoiceNudge,
  onGetNotificationNudge,
  loading,
  nudgeExecuted,
  notificationSent,
  notificationPermission,
  onRequestNotificationPermission,
  agentMode,
  onAgentModeChange,
  lastNudgeType,
  pomodoroTimer
}) => {
  return (
    <main className="dashboard">
      <div className="dashboard-content">
        <div className="dashboard-grid">
          {/* Left side: Attention Score + Buttons */}
          <div className="attention-section">
            <h2 className="section-title">Attention Score</h2>
            
            <div className="agent-toggle">
              <button
                type="button"
                className={`agent-toggle-button ${agentMode === 'goggins' ? 'active' : ''}`}
                onClick={() => onAgentModeChange('goggins')}
                disabled={loading && agentMode === 'goggins'}
              >
                💪 Goggins Coach
              </button>
              <button
                type="button"
                className={`agent-toggle-button ${agentMode === 'health' ? 'active' : ''}`}
                onClick={() => onAgentModeChange('health')}
                disabled={loading && agentMode === 'health'}
              >
                🩺 Health & Focus Boost
              </button>
            </div>

            {/* Attention Score Circle and Auto Nudge Info side by side */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem', marginBottom: '1.5rem' }}>
              <AttentionScore score={attentionScore} />

              {agentMode === 'goggins' ? (
                <div className="auto-nudge-info" style={{ flex: 1, marginBottom: 0 }}>
                  🎤 <strong>Auto Voice Nudge:</strong> Every time your attention drops, David Goggins will automatically motivate you with a new message and read it aloud!
                </div>
              ) : (
                <div className="auto-nudge-info health-mode" style={{ flex: 1, marginBottom: 0 }}>
                  🩺 <strong>Health & Focus Boost:</strong> Drops in focus trigger instant micro-interventions to reset your body and attention.
                </div>
              )}
            </div>

            {/* Buttons below */}
            <div className="nudge-buttons">

              <button
                className={`voice-nudge-button ${agentMode === 'health' ? 'health-mode' : ''} ${nudgeExecuted ? 'nudge-executed' : ''}`}
                onClick={onGetVoiceNudge}
                disabled={loading}
                title={
                  agentMode === 'health'
                    ? 'Get a science-backed micro-intervention to refresh your focus'
                    : 'Get a new voice nudge (happens automatically when attention drops)'
                }
              >
                {loading
                  ? 'Loading...'
                  : agentMode === 'health'
                  ? 'Get Health Boost ⚕️'
                  : 'Get Motivation ⚡'}
              </button>

              <button
                className={`notification-nudge-button ${notificationSent ? 'notification-sent' : ''} ${notificationPermission === 'denied' ? 'permission-denied' : ''}`}
                onClick={notificationPermission === 'granted' ? onGetNotificationNudge : onRequestNotificationPermission}
                disabled={loading}
                title={
                  notificationPermission === 'granted' 
                    ? 'Send browser notification' 
                    : notificationPermission === 'denied'
                    ? 'Notifications blocked - check browser settings'
                    : 'Click to enable notifications'
                }
              >
                {loading ? 'Loading...' : 
                 notificationPermission === 'granted' ? 'Notification Nudge 🔔' :
                 notificationPermission === 'denied' ? 'Notifications Blocked 🚫' :
                 'Enable Notifications 🔔'}
              </button>
            </div>
            
            {nudgeExecuted && lastNudgeType === 'voice' && (
              <div className="nudge-indicator voice-indicator">
                🎤 Voice Nudge Executed! Audio Playing...
              </div>
            )}

            {nudgeExecuted && lastNudgeType === 'health' && (
              <div className="nudge-indicator health-indicator">
                🩺 Health Boost Sent! Follow the action now.
              </div>
            )}

            {notificationSent && (
              <div className="nudge-indicator notification-indicator">
                🔔 Browser Notification Sent! Check your notifications.
              </div>
            )}
            
            {/* Debug: Permission status */}
            <div style={{
              marginTop: '1rem',
              padding: '0.5rem',
              background: 'rgba(0, 168, 255, 0.1)',
              border: '1px solid rgba(0, 168, 255, 0.2)',
              borderRadius: '8px',
              fontSize: '0.75rem',
              color: '#7dd3fc'
            }}>
              🔐 Notification Permission: <strong>{notificationPermission}</strong>
              {notificationPermission === 'denied' && (
                <div style={{ marginTop: '0.25rem', color: '#ef4444' }}>
                  ⚠️ To enable: Click the lock icon in address bar → Allow notifications
                </div>
              )}
            </div>
          </div>
          
          {/* Right side: Pomodoro Timer */}
          <div className="pomodoro-section">
            {pomodoroTimer}
          </div>
        </div>
      </div>
    </main>
  );
};

export default Dashboard;
