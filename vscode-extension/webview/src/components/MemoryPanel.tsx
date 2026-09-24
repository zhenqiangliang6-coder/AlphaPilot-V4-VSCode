import React, { useState, useEffect } from 'react';
import { MemoryItem, MemoryType, MemoryStatus, MemoryQueryParams } from '../utils/memoryTypes';

/**
 * AlphaPilot 记忆管理面板主组件
 * 
 * 功能：
 * - 查看记忆列表（按类型、时间、标签筛选）
 * - 编辑记忆（修改内容、调整重要性、添加标签）
 * - 删除记忆（单条/批量删除）
 * - 展示记忆统计信息
 */

const MemoryPanel: React.FC = () => {
  // 状态管理
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [selectedMemories, setSelectedMemories] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // 筛选状态
  const [filterType, setFilterType] = useState<MemoryType | 'all'>('all');
  const [filterStatus, setFilterStatus] = useState<MemoryStatus | 'all'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState<'created_at' | 'importance_score' | 'activation_score'>('created_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  
  // 编辑状态
  const [editingMemory, setEditingMemory] = useState<MemoryItem | null>(null);
  const [showEditModal, setShowEditModal] = useState(false);

  // 加载记忆列表
  useEffect(() => {
    loadMemories();
  }, [filterType, filterStatus, sortBy, sortOrder]);

  const loadMemories = async () => {
    setLoading(true);
    setError(null);
    
    try {
      // TODO: 实际项目中应该调用后端 API
      // 这里使用模拟数据
      const mockMemories: MemoryItem[] = [
        {
          id: '1',
          user_id: 'default_user',
          content: '用户偏好使用 Python 进行开发，喜欢函数式编程风格',
          summary: 'Python 开发偏好',
          memory_type: MemoryType.PREFERENCE,
          domain_tags: ['python', 'coding-style'],
          importance_score: 0.9,
          activation_score: 0.85,
          access_count: 15,
          last_accessed_at: new Date(Date.now() - 1000 * 60 * 60 * 24).toISOString(),
          created_at: new Date(Date.now() - 1000 * 60 * 60 * 24 * 7).toISOString(),
          status: MemoryStatus.ACTIVE
        },
        {
          id: '2',
          user_id: 'default_user',
          content: '成功实现了快速排序算法，时间复杂度 O(n log n)',
          summary: '快速排序实现经验',
          memory_type: MemoryType.SKILL,
          domain_tags: ['algorithm', 'sorting'],
          importance_score: 0.7,
          activation_score: 0.6,
          access_count: 8,
          last_accessed_at: new Date(Date.now() - 1000 * 60 * 60 * 24 * 3).toISOString(),
          created_at: new Date(Date.now() - 1000 * 60 * 60 * 24 * 14).toISOString(),
          status: MemoryStatus.ACTIVE
        },
        {
          id: '3',
          user_id: 'default_user',
          content: 'Docker 容器化部署 PostgreSQL 时需要注意端口映射',
          summary: 'Docker PostgreSQL 部署经验',
          memory_type: MemoryType.INSIGHT,
          domain_tags: ['docker', 'postgresql', 'deployment'],
          importance_score: 0.8,
          activation_score: 0.75,
          access_count: 12,
          last_accessed_at: new Date(Date.now() - 1000 * 60 * 60 * 24 * 2).toISOString(),
          created_at: new Date(Date.now() - 1000 * 60 * 60 * 24 * 30).toISOString(),
          status: MemoryStatus.ACTIVE
        }
      ];
      
      // 模拟 API 延迟
      await new Promise(resolve => setTimeout(resolve, 500));
      
      // 应用筛选
      let filtered = mockMemories;
      
      if (filterType !== 'all') {
        filtered = filtered.filter(m => m.memory_type === filterType);
      }
      
      if (filterStatus !== 'all') {
        filtered = filtered.filter(m => m.status === filterStatus);
      }
      
      if (searchQuery) {
        const query = searchQuery.toLowerCase();
        filtered = filtered.filter(m => 
          m.content.toLowerCase().includes(query) ||
          m.summary?.toLowerCase().includes(query) ||
          m.domain_tags.some(tag => tag.toLowerCase().includes(query))
        );
      }
      
      // 排序
      filtered.sort((a, b) => {
        const aVal = a[sortBy];
        const bVal = b[sortBy];
        if (sortOrder === 'asc') {
          return aVal > bVal ? 1 : -1;
        } else {
          return aVal < bVal ? 1 : -1;
        }
      });
      
      setMemories(filtered);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载记忆列表失败');
    } finally {
      setLoading(false);
    }
  };

  // 选择/取消选择记忆
  const toggleSelectMemory = (id: string) => {
    const newSelected = new Set(selectedMemories);
    if (newSelected.has(id)) {
      newSelected.delete(id);
    } else {
      newSelected.add(id);
    }
    setSelectedMemories(newSelected);
  };

  // 全选/取消全选
  const toggleSelectAll = () => {
    if (selectedMemories.size === memories.length) {
      setSelectedMemories(new Set());
    } else {
      setSelectedMemories(new Set(memories.map(m => m.id)));
    }
  };

  // 删除选中的记忆
  const handleDeleteSelected = async () => {
    if (selectedMemories.size === 0) return;
    
    const confirmed = window.confirm(`确定要删除选中的 ${selectedMemories.size} 条记忆吗？`);
    if (!confirmed) return;
    
    // TODO: 实际项目中应该调用后端 API
    console.log('删除记忆:', Array.from(selectedMemories));
    setMemories(memories.filter(m => !selectedMemories.has(m.id)));
    setSelectedMemories(new Set());
  };

  // 编辑记忆
  const handleEditMemory = (memory: MemoryItem) => {
    setEditingMemory(memory);
    setShowEditModal(true);
  };

  // 保存编辑
  const handleSaveEdit = async (updatedMemory: MemoryItem) => {
    // TODO: 实际项目中应该调用后端 API
    console.log('保存记忆:', updatedMemory);
    setMemories(memories.map(m => m.id === updatedMemory.id ? updatedMemory : m));
    setShowEditModal(false);
    setEditingMemory(null);
  };

  // 获取记忆类型的显示名称和颜色
  const getMemoryTypeInfo = (type: MemoryType) => {
    const info: Record<MemoryType, { label: string; color: string; icon: string }> = {
      [MemoryType.PREFERENCE]: { label: '偏好', color: 'bg-blue-500', icon: '⭐' },
      [MemoryType.FACT]: { label: '事实', color: 'bg-green-500', icon: '📚' },
      [MemoryType.SKILL]: { label: '技能', color: 'bg-purple-500', icon: '🛠️' },
      [MemoryType.CONVERSATION]: { label: '对话', color: 'bg-yellow-500', icon: '💬' },
      [MemoryType.INSIGHT]: { label: '洞察', color: 'bg-pink-500', icon: '💡' }
    };
    return info[type] || { label: type, color: 'bg-gray-500', icon: '📝' };
  };

  // 获取状态显示信息
  const getStatusInfo = (status: MemoryStatus) => {
    const info: Record<MemoryStatus, { label: string; color: string }> = {
      [MemoryStatus.ACTIVE]: { label: '活跃', color: 'text-green-500' },
      [MemoryStatus.ARCHIVED]: { label: '归档', color: 'text-gray-500' },
      [MemoryStatus.PRUNED]: { label: '已剪枝', color: 'text-red-500' },
      [MemoryStatus.MERGED]: { label: '已合并', color: 'text-blue-500' }
    };
    return info[status] || { label: status, color: 'text-gray-500' };
  };

  return (
    <div className="flex flex-col h-full bg-[var(--vscode-editor-background)] text-[var(--vscode-editor-foreground)]">
      {/* 头部工具栏 */}
      <div className="flex items-center justify-between p-4 border-b border-[var(--vscode-panel-border)]">
        <div className="flex items-center gap-2">
          <span className="text-lg font-semibold">🧠 记忆管理</span>
          <span className="text-sm text-[var(--vscode-descriptionForeground)]">
            ({memories.length} 条记忆)
          </span>
        </div>
        
        <div className="flex items-center gap-2">
          {selectedMemories.size > 0 && (
            <button
              onClick={handleDeleteSelected}
              className="px-3 py-1 bg-red-500 hover:bg-red-600 text-white rounded text-sm"
            >
              删除选中 ({selectedMemories.size})
            </button>
          )}
        </div>
      </div>

      {/* 筛选栏 */}
      <div className="flex flex-wrap items-center gap-3 p-4 border-b border-[var(--vscode-panel-border)]">
        {/* 类型筛选 */}
        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value as MemoryType | 'all')}
          className="px-3 py-1 bg-[var(--vscode-dropdown-background)] text-[var(--vscode-dropdown-foreground)] border border-[var(--vscode-dropdown-border)] rounded text-sm"
        >
          <option value="all">所有类型</option>
          <option value={MemoryType.PREFERENCE}>⭐ 偏好</option>
          <option value={MemoryType.FACT}>📚 事实</option>
          <option value={MemoryType.SKILL}>🛠️ 技能</option>
          <option value={MemoryType.CONVERSATION}>💬 对话</option>
          <option value={MemoryType.INSIGHT}>💡 洞察</option>
        </select>

        {/* 状态筛选 */}
        <select
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value as MemoryStatus | 'all')}
          className="px-3 py-1 bg-[var(--vscode-dropdown-background)] text-[var(--vscode-dropdown-foreground)] border border-[var(--vscode-dropdown-border)] rounded text-sm"
        >
          <option value="all">所有状态</option>
          <option value={MemoryStatus.ACTIVE}>活跃</option>
          <option value={MemoryStatus.ARCHIVED}>归档</option>
          <option value={MemoryStatus.PRUNED}>已剪枝</option>
          <option value={MemoryStatus.MERGED}>已合并</option>
        </select>

        {/* 搜索框 */}
        <input
          type="text"
          placeholder="搜索记忆..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="px-3 py-1 bg-[var(--vscode-input-background)] text-[var(--vscode-input-foreground)] border border-[var(--vscode-input-border)] rounded text-sm flex-1 min-w-[200px]"
        />

        {/* 排序 */}
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as any)}
          className="px-3 py-1 bg-[var(--vscode-dropdown-background)] text-[var(--vscode-dropdown-foreground)] border border-[var(--vscode-dropdown-border)] rounded text-sm"
        >
          <option value="created_at">创建时间</option>
          <option value="importance_score">重要性</option>
          <option value="activation_score">激活度</option>
        </select>

        <button
          onClick={() => setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')}
          className="px-3 py-1 bg-[var(--vscode-button-secondaryBackground)] hover:bg-[var(--vscode-button-secondaryHoverBackground)] text-[var(--vscode-button-secondaryForeground)] rounded text-sm"
        >
          {sortOrder === 'asc' ? '↑' : '↓'}
        </button>
      </div>

      {/* 记忆列表 */}
      <div className="flex-1 overflow-y-auto p-4">
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-[var(--vscode-descriptionForeground)]">加载中...</div>
          </div>
        ) : error ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-red-500">{error}</div>
          </div>
        ) : memories.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-[var(--vscode-descriptionForeground)]">暂无记忆</div>
          </div>
        ) : (
          <div className="space-y-3">
            {/* 全选 */}
            <div className="flex items-center gap-2 pb-2 border-b border-[var(--vscode-panel-border)]">
              <input
                type="checkbox"
                checked={selectedMemories.size === memories.length && memories.length > 0}
                onChange={toggleSelectAll}
                className="w-4 h-4"
              />
              <span className="text-sm text-[var(--vscode-descriptionForeground)]">
                全选 ({selectedMemories.size}/{memories.length})
              </span>
            </div>

            {/* 记忆条目 */}
            {memories.map((memory) => {
              const typeInfo = getMemoryTypeInfo(memory.memory_type);
              const statusInfo = getStatusInfo(memory.status);
              
              return (
                <div
                  key={memory.id}
                  className="flex items-start gap-3 p-3 bg-[var(--vscode-editor-inactiveSelectionBackground)] rounded-lg hover:bg-[var(--vscode-list-hoverBackground)] transition-colors"
                >
                  {/* 选择框 */}
                  <input
                    type="checkbox"
                    checked={selectedMemories.has(memory.id)}
                    onChange={() => toggleSelectMemory(memory.id)}
                    className="w-4 h-4 mt-1"
                  />

                  {/* 记忆内容 */}
                  <div className="flex-1 min-w-0">
                    {/* 标题行 */}
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`${typeInfo.color} text-white px-2 py-0.5 rounded text-xs`}>
                        {typeInfo.icon} {typeInfo.label}
                      </span>
                      <span className={`text-xs ${statusInfo.color}`}>
                        {statusInfo.label}
                      </span>
                      <span className="text-xs text-[var(--vscode-descriptionForeground)]">
                        重要性: {(memory.importance_score * 100).toFixed(0)}%
                      </span>
                      <span className="text-xs text-[var(--vscode-descriptionForeground)]">
                        激活度: {(memory.activation_score * 100).toFixed(0)}%
                      </span>
                    </div>

                    {/* 内容 */}
                    <div className="text-sm mb-2 line-clamp-2">
                      {memory.summary || memory.content}
                    </div>

                    {/* 标签 */}
                    <div className="flex flex-wrap gap-1">
                      {memory.domain_tags.map((tag, index) => (
                        <span
                          key={index}
                          className="px-2 py-0.5 bg-[var(--vscode-badge-background)] text-[var(--vscode-badge-foreground)] rounded text-xs"
                        >
                          #{tag}
                        </span>
                      ))}
                    </div>

                    {/* 元信息 */}
                    <div className="flex items-center gap-4 mt-2 text-xs text-[var(--vscode-descriptionForeground)]">
                      <span>访问 {memory.access_count} 次</span>
                      <span>创建于 {new Date(memory.created_at).toLocaleDateString()}</span>
                    </div>
                  </div>

                  {/* 操作按钮 */}
                  <div className="flex flex-col gap-2">
                    <button
                      onClick={() => handleEditMemory(memory)}
                      className="px-3 py-1 bg-[var(--vscode-button-background)] hover:bg-[var(--vscode-button-hoverBackground)] text-[var(--vscode-button-foreground)] rounded text-xs"
                    >
                      编辑
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 编辑模态框 */}
      {showEditModal && editingMemory && (
        <MemoryEditModal
          memory={editingMemory}
          onSave={handleSaveEdit}
          onClose={() => {
            setShowEditModal(false);
            setEditingMemory(null);
          }}
        />
      )}
    </div>
  );
};

// ============================================================
// 编辑模态框组件
// ============================================================
interface MemoryEditModalProps {
  memory: MemoryItem;
  onSave: (memory: MemoryItem) => void;
  onClose: () => void;
}

const MemoryEditModal: React.FC<MemoryEditModalProps> = ({ memory, onSave, onClose }) => {
  const [content, setContent] = useState(memory.content);
  const [summary, setSummary] = useState(memory.summary || '');
  const [importance, setImportance] = useState(memory.importance_score);
  const [tags, setTags] = useState(memory.domain_tags.join(', '));

  const handleSave = () => {
    const updated: MemoryItem = {
      ...memory,
      content,
      summary: summary || undefined,
      importance_score: importance,
      domain_tags: tags.split(',').map(t => t.trim()).filter(t => t)
    };
    onSave(updated);
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-[var(--vscode-editor-background)] border border-[var(--vscode-panel-border)] rounded-lg p-6 w-full max-w-2xl max-h-[80vh] overflow-y-auto">
        <h2 className="text-lg font-semibold mb-4">编辑记忆</h2>

        {/* 内容 */}
        <div className="mb-4">
          <label className="block text-sm mb-1">内容</label>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="w-full px-3 py-2 bg-[var(--vscode-input-background)] text-[var(--vscode-input-foreground)] border border-[var(--vscode-input-border)] rounded text-sm"
            rows={4}
          />
        </div>

        {/* 摘要 */}
        <div className="mb-4">
          <label className="block text-sm mb-1">摘要</label>
          <input
            type="text"
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            className="w-full px-3 py-2 bg-[var(--vscode-input-background)] text-[var(--vscode-input-foreground)] border border-[var(--vscode-input-border)] rounded text-sm"
          />
        </div>

        {/* 重要性 */}
        <div className="mb-4">
          <label className="block text-sm mb-1">重要性: {(importance * 100).toFixed(0)}%</label>
          <input
            type="range"
            min="0"
            max="1"
            step="0.1"
            value={importance}
            onChange={(e) => setImportance(parseFloat(e.target.value))}
            className="w-full"
          />
        </div>

        {/* 标签 */}
        <div className="mb-4">
          <label className="block text-sm mb-1">标签（逗号分隔）</label>
          <input
            type="text"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            className="w-full px-3 py-2 bg-[var(--vscode-input-background)] text-[var(--vscode-input-foreground)] border border-[var(--vscode-input-border)] rounded text-sm"
          />
        </div>

        {/* 按钮 */}
        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-[var(--vscode-button-secondaryBackground)] hover:bg-[var(--vscode-button-secondaryHoverBackground)] text-[var(--vscode-button-secondaryForeground)] rounded"
          >
            取消
          </button>
          <button
            onClick={handleSave}
            className="px-4 py-2 bg-[var(--vscode-button-background)] hover:bg-[var(--vscode-button-hoverBackground)] text-[var(--vscode-button-foreground)] rounded"
          >
            保存
          </button>
        </div>
      </div>
    </div>
  );
};

export default MemoryPanel;
