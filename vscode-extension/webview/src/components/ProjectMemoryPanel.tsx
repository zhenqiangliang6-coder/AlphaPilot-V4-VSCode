// src/components/ProjectMemoryPanel.tsx
import React, { useEffect, useState } from 'react';

interface Memory {
  id: number;
  type: string;
  content: string;
  importance: number;
  created_at: string;
}

interface ProjectMemoryPanelProps {
  projectId: number;
  projectName: string;
  onClose: () => void;
}

export const ProjectMemoryPanel: React.FC<ProjectMemoryPanelProps> = ({ 
  projectId, 
  projectName,
  onClose 
}) => {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>('all');

  useEffect(() => {
    loadProjectMemories();
  }, [projectId]);

  const loadProjectMemories = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const response = await fetch(`http://localhost:3000/projects/${projectId}/memories?limit=50`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      setMemories(data.memories || []);
    } catch (err) {
      console.error('Failed to load project memories:', err);
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

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'rule': return '📏';
      case 'preference': return '⚙️';
      case 'pattern': return '🔧';
      case 'summary': return '📝';
      default: return '💡';
    }
  };

  const getTypeColor = (type: string) => {
    switch (type) {
      case 'rule': return '#3b82f6'; // blue
      case 'preference': return '#10b981'; // green
      case 'pattern': return '#f59e0b'; // yellow
      case 'summary': return '#8b5cf6'; // purple
      default: return '#6b7280'; // gray
    }
  };

  const filteredMemories = filter === 'all' 
    ? memories 
    : memories.filter(m => m.type === filter);

  if (loading) {
    return (
      <div className="project-memory-panel">
        <div className="panel-header">
          <h3>🧠 项目记忆</h3>
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
      <div className="project-memory-panel">
        <div className="panel-header">
          <h3>🧠 项目记忆</h3>
          <button onClick={onClose} className="close-btn">×</button>
        </div>
        <div className="panel-content error">
          <p>❌ {error}</p>
          <button onClick={loadProjectMemories} className="retry-btn">重试</button>
        </div>
      </div>
    );
  }

  return (
    <div className="project-memory-panel">
      <div className="panel-header">
        <h3>🧠 项目记忆</h3>
        <button onClick={onClose} className="close-btn">×</button>
      </div>
      
      <div className="project-info">
        <span className="project-label">项目:</span>
        <span className="project-name">{projectName}</span>
      </div>
      
      <div className="filter-bar">
        <button 
          className={`filter-btn ${filter === 'all' ? 'active' : ''}`}
          onClick={() => setFilter('all')}
        >
          全部
        </button>
        <button 
          className={`filter-btn ${filter === 'rule' ? 'active' : ''}`}
          onClick={() => setFilter('rule')}
        >
          📏 规则
        </button>
        <button 
          className={`filter-btn ${filter === 'preference' ? 'active' : ''}`}
          onClick={() => setFilter('preference')}
        >
          ⚙️ 偏好
        </button>
        <button 
          className={`filter-btn ${filter === 'pattern' ? 'active' : ''}`}
          onClick={() => setFilter('pattern')}
        >
          🔧 模式
        </button>
      </div>
      
      <div className="panel-content">
        {filteredMemories.length === 0 ? (
          <div className="empty-state">
            <p>暂无记忆数据</p>
          </div>
        ) : (
          <div className="memory-list">
            {filteredMemories.map((memory) => (
              <div key={memory.id} className="memory-item">
                <div className="memory-header">
                  <span className="memory-type-badge" style={{ 
                    backgroundColor: getTypeColor(memory.type) 
                  }}>
                    {getTypeIcon(memory.type)} {memory.type}
                  </span>
                  <span className="memory-importance">
                    重要性: {memory.importance}/10
                  </span>
                </div>
                
                <div className="memory-content">
                  {memory.content}
                </div>
                
                <div className="memory-footer">
                  <span className="memory-time">
                    {formatDate(memory.created_at)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      
      <style>{`
        .project-memory-panel {
          position: fixed;
          right: 0;
          top: 0;
          width: 450px;
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
        
        .project-info {
          padding: 8px 16px;
          background: var(--vscode-editor-inactiveSelectionBackground);
          border-bottom: 1px solid var(--vscode-panel-border);
          font-size: 12px;
        }
        
        .project-label {
          color: var(--vscode-descriptionForeground);
          margin-right: 8px;
        }
        
        .project-name {
          color: var(--vscode-foreground);
          font-weight: bold;
        }
        
        .filter-bar {
          padding: 8px 16px;
          border-bottom: 1px solid var(--vscode-panel-border);
          display: flex;
          gap: 8px;
          overflow-x: auto;
        }
        
        .filter-btn {
          padding: 4px 12px;
          background: var(--vscode-button-secondaryBackground);
          color: var(--vscode-button-secondaryForeground);
          border: none;
          border-radius: 4px;
          cursor: pointer;
          font-size: 12px;
          white-space: nowrap;
        }
        
        .filter-btn:hover {
          background: var(--vscode-button-secondaryHoverBackground);
        }
        
        .filter-btn.active {
          background: var(--vscode-button-background);
          color: var(--vscode-button-foreground);
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
        
        .memory-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }
        
        .memory-item {
          padding: 12px;
          background: var(--vscode-editor-inactiveSelectionBackground);
          border-radius: 6px;
          border: 1px solid var(--vscode-panel-border);
        }
        
        .memory-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 8px;
        }
        
        .memory-type-badge {
          padding: 2px 8px;
          border-radius: 12px;
          font-size: 11px;
          color: white;
          text-transform: uppercase;
        }
        
        .memory-importance {
          font-size: 11px;
          color: var(--vscode-descriptionForeground);
        }
        
        .memory-content {
          font-size: 13px;
          color: var(--vscode-foreground);
          line-height: 1.6;
          margin-bottom: 8px;
          white-space: pre-wrap;
        }
        
        .memory-footer {
          font-size: 11px;
          color: var(--vscode-descriptionForeground);
        }
        
        .memory-time {
          display: block;
        }
      `}</style>
    </div>
  );
};
