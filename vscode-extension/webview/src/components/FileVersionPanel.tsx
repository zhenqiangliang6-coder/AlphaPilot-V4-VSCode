// src/components/FileVersionPanel.tsx
import React, { useEffect, useState } from 'react';

interface FileVersion {
  id: number;
  file_id: number;
  content: string;
  hash?: string;
  created_at: string;
  task?: {
    id: string;
    prompt: string;
    created_at: string;
  };
}

interface FileVersionPanelProps {
  fileId: number;
  filePath: string;
  onClose: () => void;
}

export const FileVersionPanel: React.FC<FileVersionPanelProps> = ({ 
  fileId, 
  filePath, 
  onClose 
}) => {
  const [versions, setVersions] = useState<FileVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedVersion, setSelectedVersion] = useState<FileVersion | null>(null);

  useEffect(() => {
    loadFileVersions();
  }, [fileId]);

  const loadFileVersions = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const response = await fetch(`http://localhost:3000/files/${fileId}/versions?limit=20`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      setVersions(data.versions || []);
    } catch (err) {
      console.error('Failed to load file versions:', err);
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

  const getContentPreview = (content: string) => {
    const lines = content.split('\n');
    return lines.slice(0, 5).join('\n') + (lines.length > 5 ? '\n...' : '');
  };

  if (loading) {
    return (
      <div className="file-version-panel">
        <div className="panel-header">
          <h3>📄 文件版本</h3>
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
      <div className="file-version-panel">
        <div className="panel-header">
          <h3>📄 文件版本</h3>
          <button onClick={onClose} className="close-btn">×</button>
        </div>
        <div className="panel-content error">
          <p>❌ {error}</p>
          <button onClick={loadFileVersions} className="retry-btn">重试</button>
        </div>
      </div>
    );
  }

  return (
    <div className="file-version-panel">
      <div className="panel-header">
        <h3>📄 文件版本</h3>
        <button onClick={onClose} className="close-btn">×</button>
      </div>
      
      <div className="file-path">
        <span className="path-label">路径:</span>
        <span className="path-value">{filePath}</span>
      </div>
      
      <div className="panel-content">
        {versions.length === 0 ? (
          <div className="empty-state">
            <p>暂无版本历史</p>
          </div>
        ) : (
          <div className="version-list">
            {versions.map((version, index) => (
              <div 
                key={version.id} 
                className={`version-item ${selectedVersion?.id === version.id ? 'selected' : ''}`}
                onClick={() => setSelectedVersion(version)}
              >
                <div className="version-header">
                  <span className="version-number">v{versions.length - index}</span>
                  <span className="version-time">{formatDate(version.created_at)}</span>
                </div>
                
                {version.task && (
                  <div className="version-task">
                    <span className="task-label">任务:</span>
                    <span className="task-prompt">{version.task.prompt?.substring(0, 60)}...</span>
                  </div>
                )}
                
                <div className="version-preview">
                  <pre>{getContentPreview(version.content)}</pre>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      
      {selectedVersion && (
        <div className="version-detail">
          <div className="detail-header">
            <h4>版本详情</h4>
            <button onClick={() => setSelectedVersion(null)} className="close-detail-btn">×</button>
          </div>
          <div className="detail-content">
            <pre>{selectedVersion.content}</pre>
          </div>
        </div>
      )}
      
      <style>{`
        .file-version-panel {
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
        
        .file-path {
          padding: 8px 16px;
          background: var(--vscode-editor-inactiveSelectionBackground);
          border-bottom: 1px solid var(--vscode-panel-border);
          font-size: 12px;
        }
        
        .path-label {
          color: var(--vscode-descriptionForeground);
          margin-right: 8px;
        }
        
        .path-value {
          color: var(--vscode-foreground);
          font-family: 'Consolas', monospace;
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
        
        .version-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }
        
        .version-item {
          padding: 12px;
          background: var(--vscode-editor-inactiveSelectionBackground);
          border-radius: 6px;
          border: 1px solid var(--vscode-panel-border);
          cursor: pointer;
          transition: all 0.2s;
        }
        
        .version-item:hover {
          background: var(--vscode-list-hoverBackground);
        }
        
        .version-item.selected {
          border-color: var(--vscode-focusBorder);
          background: var(--vscode-list-activeSelectionBackground);
        }
        
        .version-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 8px;
        }
        
        .version-number {
          padding: 2px 8px;
          background: var(--vscode-button-background);
          color: var(--vscode-button-foreground);
          border-radius: 12px;
          font-size: 11px;
          font-weight: bold;
        }
        
        .version-time {
          font-size: 11px;
          color: var(--vscode-descriptionForeground);
        }
        
        .version-task {
          margin-bottom: 8px;
          font-size: 12px;
        }
        
        .task-label {
          color: var(--vscode-descriptionForeground);
          margin-right: 4px;
        }
        
        .task-prompt {
          color: var(--vscode-foreground);
        }
        
        .version-preview {
          background: var(--vscode-editor-background);
          padding: 8px;
          border-radius: 4px;
          border: 1px solid var(--vscode-panel-border);
        }
        
        .version-preview pre {
          margin: 0;
          font-size: 11px;
          color: var(--vscode-editor-foreground);
          font-family: 'Consolas', monospace;
          white-space: pre-wrap;
          word-break: break-word;
        }
        
        .version-detail {
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          background: var(--vscode-editor-background);
          display: flex;
          flex-direction: column;
          z-index: 10;
        }
        
        .detail-header {
          padding: 12px 16px;
          border-bottom: 1px solid var(--vscode-panel-border);
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        
        .detail-header h4 {
          margin: 0;
          font-size: 14px;
          color: var(--vscode-foreground);
        }
        
        .close-detail-btn {
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
        
        .detail-content {
          flex: 1;
          overflow-y: auto;
          padding: 16px;
        }
        
        .detail-content pre {
          margin: 0;
          font-size: 13px;
          color: var(--vscode-editor-foreground);
          font-family: 'Consolas', monospace;
          white-space: pre-wrap;
          word-break: break-word;
          line-height: 1.6;
        }
      `}</style>
    </div>
  );
};
