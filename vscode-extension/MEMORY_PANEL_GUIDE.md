# 🧠 AlphaPilot 记忆中枢 - 阶段 3 实施文档

> **前端记忆管理面板**  
> 在 VS Code 扩展里提供直观的记忆管理界面

---

## 📋 实施概览

**完成时间**: 2026-09-21  
**技术栈**: React + TypeScript + Tailwind CSS  
**状态**: ✅ 基础组件已完成

---

## 🎯 功能清单

### ✅ 已完成功能

| 功能 | 状态 | 说明 |
|------|------|------|
| **查看记忆列表** | ✅ | 支持按类型、状态、时间、重要性筛选 |
| **搜索记忆** | ✅ | 支持内容、摘要、标签搜索 |
| **编辑记忆** | ✅ | 修改内容、摘要、重要性、标签 |
| **删除记忆** | ✅ | 单条删除和批量删除 |
| **排序** | ✅ | 按创建时间、重要性、激活度排序 |
| **类型筛选** | ✅ | 偏好/事实/技能/对话/洞察 |
| **状态筛选** | ✅ | 活跃/归档/已剪枝/已合并 |

### ⏳ 待完成功能

| 功能 | 状态 | 说明 |
|------|------|------|
| **记忆关联图谱** | ⏳ | 可视化记忆之间的关系 |
| **后端 API 集成** | ⏳ | 连接 Node API 进行真实数据操作 |
| **记忆统计面板** | ⏳ | 展示记忆分布和趋势 |

---

## 📁 文件清单

### 新增文件

| 文件 | 说明 |
|------|------|
| [`memoryTypes.ts`](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\vscode-extension\webview\src\utils\memoryTypes.ts) | 记忆相关类型定义 |
| [`MemoryPanel.tsx`](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\vscode-extension\webview\src\components\MemoryPanel.tsx) | 记忆管理面板主组件 |
| [`MEMORY_PANEL_GUIDE.md`](file://d:\Copilot_Alphapilot\Copilot_Alphapilot\vscode-extension\MEMORY_PANEL_GUIDE.md) | 本文档 |

### 待修改文件

| 文件 | 修改内容 |
|------|----------|
| `App.tsx` | 添加记忆面板路由 |
| `extension.ts` | 注册打开记忆面板命令 |
| `reactPanel.ts` | 添加记忆面板消息处理 |

---

## 🚀 使用指南

### 1. 在 App.tsx 中添加路由

```typescript
import MemoryPanel from './components/MemoryPanel';

function App() {
  const [currentView, setCurrentView] = useState<'chat' | 'memory'>('chat');

  return (
    <div className="flex flex-col h-screen">
      <Toolbar onSwitchView={setCurrentView} currentView={currentView} />
      
      {currentView === 'chat' ? (
        <MessageList />
      ) : (
        <MemoryPanel />
      )}
      
      <ChatInput />
    </div>
  );
}
```

### 2. 在 extension.ts 中注册命令

```typescript
context.subscriptions.push(
  vscode.commands.registerCommand('alphaMinimalExtension.openMemoryPanel', () => {
    ReactPanel.createOrShow(context.extensionUri, { action: 'openMemoryPanel' });
  })
);
```

### 3. 在 Toolbar 中添加切换按钮

```typescript
interface ToolbarProps {
  onSwitchView: (view: 'chat' | 'memory') => void;
  currentView: 'chat' | 'memory';
}

const Toolbar: React.FC<ToolbarProps> = ({ onSwitchView, currentView }) => {
  return (
    <div className="flex items-center justify-between p-2 border-b">
      <div className="flex items-center gap-2">
        <button
          onClick={() => onSwitchView('chat')}
          className={`px-3 py-1 rounded ${currentView === 'chat' ? 'bg-blue-500 text-white' : ''}`}
        >
          💬 聊天
        </button>
        <button
          onClick={() => onSwitchView('memory')}
          className={`px-3 py-1 rounded ${currentView === 'memory' ? 'bg-blue-500 text-white' : ''}`}
        >
          🧠 记忆
        </button>
      </div>
    </div>
  );
};
```

---

## 🎨 组件架构

```
MemoryPanel (主组件)
├── 头部工具栏
│   ├── 标题和统计
│   └── 批量操作按钮
├── 筛选栏
│   ├── 类型筛选 (select)
│   ├── 状态筛选 (select)
│   ├── 搜索框 (input)
│   ├── 排序选择 (select)
│   └── 排序方向 (button)
├── 记忆列表
│   ├── 全选复选框
│   └── 记忆条目 (map)
│       ├── 选择复选框
│       ├── 类型标签
│       ├── 状态标签
│       ├── 重要性/激活度
│       ├── 内容摘要
│       ├── 领域标签
│       ├── 元信息
│       └── 编辑按钮
└── 编辑模态框 (MemoryEditModal)
    ├── 内容编辑 (textarea)
    ├── 摘要编辑 (input)
    ├── 重要性滑块 (range)
    ├── 标签编辑 (input)
    └── 保存/取消按钮
```

---

## 📊 数据类型

### MemoryItem

```typescript
interface MemoryItem {
  id: string;
  user_id: string;
  content: string;
  summary?: string;
  memory_type: MemoryType;        // preference/fact/skill/conversation/insight
  domain_tags: string[];
  importance_score: number;       // 0~1
  activation_score: number;       // 0~1
  access_count: number;
  last_accessed_at: string;
  created_at: string;
  status: MemoryStatus;           // active/archived/pruned/merged
}
```

### MemoryType 枚举

```typescript
enum MemoryType {
  PREFERENCE = 'preference',      // 用户偏好 ⭐
  FACT = 'fact',                  // 事实知识 📚
  SKILL = 'skill',                // 技能经验 🛠️
  CONVERSATION = 'conversation',  // 对话记忆 💬
  INSIGHT = 'insight'             // 洞察领悟 💡
}
```

---

## 🔌 后端 API 集成

### 待实现的 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/memory/list` | 获取记忆列表 |
| GET | `/memory/:id` | 获取单条记忆 |
| PUT | `/memory/:id` | 更新记忆 |
| DELETE | `/memory/:id` | 删除记忆 |
| DELETE | `/memory/batch` | 批量删除记忆 |
| GET | `/memory/stats` | 获取记忆统计 |
| GET | `/memory/graph` | 获取记忆关联图谱 |

### 请求示例

```typescript
// 获取记忆列表
const fetchMemories = async (params: MemoryQueryParams) => {
  const response = await fetch(`${API_URL}/memory/list?${new URLSearchParams(params)}`);
  const data: MemoryApiResponse<MemoryListResponse> = await response.json();
  return data.data;
};

// 更新记忆
const updateMemory = async (id: string, updates: Partial<MemoryItem>) => {
  const response = await fetch(`${API_URL}/memory/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates)
  });
  const data: MemoryApiResponse<MemoryItem> = await response.json();
  return data.data;
};

// 删除记忆
const deleteMemory = async (id: string) => {
  await fetch(`${API_URL}/memory/${id}`, { method: 'DELETE' });
};

// 批量删除
const deleteMemories = async (ids: string[]) => {
  await fetch(`${API_URL}/memory/batch`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids })
  });
};
```

---

## 🎯 下一步计划

### 1. 集成后端 API

- [ ] 实现 Node API 的记忆相关端点
- [ ] 在 MemoryPanel 中调用真实 API
- [ ] 处理加载状态和错误状态

### 2. 记忆关联图谱

- [ ] 使用 D3.js 或 Cytoscape.js 实现图谱可视化
- [ ] 支持拖拽交互
- [ ] 支持缩放和导航
- [ ] 展示记忆之间的关系（related_to/contradicts/depends_on/is_example_of）

### 3. 记忆统计面板

- [ ] 展示记忆类型分布
- [ ] 展示记忆状态分布
- [ ] 展示重要性/激活度分布
- [ ] 展示记忆增长趋势

---

## 🧪 测试指南

### 本地测试（使用模拟数据）

```powershell
# 进入 webview 目录
cd d:\Copilot_Alphapilot\Copilot_Alphapilot\vscode-extension\webview

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

### 集成测试

```powershell
# 编译 webview
npm run build

# 编译扩展
cd ..
npm run compile

# 启动扩展
F5
```

---

## 🎉 结语

> **"真正的技术掌控力来自于从底层构建，而非仅调用 API。"**

AlphaPilot 记忆管理面板让 AI 的记忆变得**可见、可编辑、可管理**：

✅ **透明化** - 用户可以查看 AI 记住了什么  
✅ **可控性** - 用户可以编辑或删除不准确的记忆  
✅ **可追溯** - 每条记忆都有创建时间、访问次数等元信息  
✅ **用户友好** - 直观的界面，支持筛选、搜索、排序  

**让 AlphaPilot 的记忆真正属于用户！** 🚀

---

*最后更新：2026-09-21*  
*架构师：World-Class AI Architect*  
*守护者：每一位 AlphaPilot 开发者*
