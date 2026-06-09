// src/components/TaskHistoryPanel.tsx
import React, { useEffect, useState } from 'react';
import { vscodeAPI } from '../utils/vscode';

interface Task {
  id: string;
  prompt: string;
  status: string;
  created_at: string;
  finished_at?: string;
  user?: { name: string };
  project?: { name: string };
  steps?: Array<{
    step_type: string;
    status: string;
    created_at: string;
  }>;
}

interface TaskHistoryPanelProps {
  onClose: () => void;
}

export const TaskHistoryPanel: React.FC<TaskHistoryPanelProps> = ({ onClose }) => {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadTaskHistory();
  }, []);

  const loadTaskHistory = async () => {
    try {
      setLoading(true);
      setError(null);
      
      // 调用 Node API 获取任务历史
      const response = await fetch('http://localhost:3000/tasks/history?limit=20');
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      setTasks(data.tasks || []);
    } catch (err) {
      console.error('Failed to load task history:', err);
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return '#10b981'; // green
      case 'failed': return '#ef4444'; // red
      case 'running': return '#f59e0b'; // yellow
      default: return '#6b7280'; // gray
    }
  };

  const getStepCount = (task: Task) => {
    return task.steps?.length || 0;
  };

  if (loading) {
    return (
      <div className="task-history-panel">
        <div className="panel-header">
          <h3>📋 任务历史</h3>
          <button onClick={onClose} className="close-btn">×</button>
        </div>
        <div className="panel-content loading">
          <div className="spinner"></div>
          <p>加载中...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="task-history-panel">
        <div className="panel-header">
          <h3>📋 任务历史</h3>
          <button onClick={onClose} className="close-btn">×</button>
        </div>
        <div className="panel-content error">
          <p>❌ {error}</p>
          <button onClick={loadTaskHistory} className="retry-btn">重试</button>
        </div>
      </div>
    );
  }

  return (
    <div className="task-history-panel">
      <div className="panel-header">
        <h3>📋 任务历史</h3>
        <button onClick={onClose} className="close-btn">×</button>
      </div>
      
      <div className="panel-content">
        {tasks.length === 0 ? (
          <div className="empty-state">
            <p>暂无任务历史</p>
          </div>
        ) : (
          <div className="task-list">
            {tasks.map((task) => (
              <div key={task.id} className="task-item">
                <div className="task-header">
                  <span 
                    className="task-status"
                    style={{ backgroundColor: getStatusColor(task.status) }}
                  >
                    {task.status}
                  </span>
                  <span className="task-time">
                    {formatDate(task.created_at)}
                  </span>
                </div>
                
                <div className="task-prompt">
                  {task.prompt?.substring(0, 100)}
                  {task.prompt && task.prompt.length > 100 ? '...' : ''}
                </div>
                
                <div className="task-meta">
                  {task.user && <span className="meta-item">👤 {task.user.name}</span>}
                  {task.project && <span className="meta-item">📁 {task.project.name}</span>}
                  <span className="meta-item">🔢 {getStepCount(task)} 步</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      
      <style>{`
        .task-history-panel {
          position: fixed;
          right: 0;
          top: 0;
          width: 400px;
          height: 100vh;
          background: var(--vscode-editor-background);
          border-left: 1px solid var(--vscode-panel-border);
          display: flex;
          flex-direction: column;
          z-index: 1000;
        }
        
        .panel-header {
          padding: 12px 16px;
          border-bottom: 1px solid var(--vscode-panel-border);
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        
        .panel-header h3 {
          margin: 0;
          font-size: 14px;
          color: var(--vscode-foreground);
        }
        
        .close-btn {
          background: none;
          border: none;
          color: var(--vscode-foreground);
          font-size: 20px;
          cursor: pointer;
          padding: 0;
          width: 24px;
          height: 24px;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        
        .close-btn:hover {
          background: var(--vscode-button-hoverBackground);
        }
        
        .panel-content {
          flex: 1;
          overflow-y: auto;
          padding: 12px;
        }
        
        .panel-content.loading,
        .panel-content.error {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 12px;
        }
        
        .spinner {
          width: 32px;
          height: 32px;
          border: 3px solid var(--vscode-progressBar-background);
          border-top-color: var(--vscode-progressBar-foreground);
          border-radius: 50%;
          animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
        
        .retry-btn {
          padding: 8px 16px;
          background: var(--vscode-button-background);
          color: var(--vscode-button-foreground);
          border: none;
          border-radius: 4px;
          cursor: pointer;
        }
        
        .retry-btn:hover {
          background: var(--vscode-button-hoverBackground);
        }
        
        .empty-state {
          text-align: center;
          color: var(--vscode-descriptionForeground);
          padding: 40px 20px;
        }
        
        .task-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }
        
        .task-item {
          padding: 12px;
          background: var(--vscode-editor-inactiveSelectionBackground);
          border-radius: 6px;
          border: 1px solid var(--vscode-panel-border);
        }
        
        .task-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 8px;
        }
        
        .task-status {
          padding: 2px 8px;
          border-radius: 12px;
          font-size: 11px;
          color: white;
          text-transform: uppercase;
        }
        
        .task-time {
          font-size: 11px;
          color: var(--vscode-descriptionForeground);
        }
        
        .task-prompt {
          font-size: 13px;
          color: var(--vscode-foreground);
          margin-bottom: 8px;
          line-height: 1.5;
        }
        
        .task-meta {
          display: flex;
          gap: 12px;
          font-size: 11px;
          color: var(--vscode-descriptionForeground);
        }
        
        .meta-item {
          display: flex;
          align-items: center;
          gap: 4px;
        }
      `}</style>
    </div>
  );
};
