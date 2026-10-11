# -*- coding: utf-8 -*-
# intent_router._data — 静态配置表（Intent Router Data Tables）
# 从 intent_router.py 拆分而来 — 纯数据，0 逻辑依赖

from typing import Dict

# =========================================================
# ⓪ LLM + Regex 联合路由（工业标准）
# =========================================================
ALL_INTENTS = (
    "chat", "mentor_explain", "code_review", "delete_files",
    "external_git", "workspace_maintenance", "write_code",
    "fix_code", "explain_and_fix", "explain_code",
    "creative_writing", "analysis", "architecture",
    "refactor", "generate_doc", "set_preference",
)

ALL_TARGET_TYPES = ("file", "code", "test", "config", "infra", "dep", "none")

LITE_CLASSIFY_PROMPT = """你是意图路由器。根据用户输入，只输出一个 JSON 对象，不要任何解释。

    可选意图（intent）：
    - chat: 纯对话/闲聊/问候/问好/感谢
    - mentor_explain: 需要教育性解释/教学/原理讲解
    - code_review: 代码审查/安全检查/质量评估
    - delete_files: 删除文件/目录/模块/依赖
    - workspace_maintenance: 项目级别维护（缩进/格式化/语法检查）
    - write_code: 编写/生成/创建/修改/添加 代码/文件/配置/测试/文档/模块/组件/功能
    - fix_code: 修复编译错误/类型错误/运行时错误（有明确错误信息）
    - explain_and_fix: 既解释原因又修复问题
    - explain_code: 解释代码含义/阅读代码/理解逻辑
    - creative_writing: 创作性写作（非代码）
    - analysis: 分析/性能分析/问题调查
    - architecture: 架构设计/方案讨论（只读，不写代码）
    - refactor: 重构/抽取/拆分/迁移（改进现有代码结构）
    - generate_doc: 生成文档/注释/API文档
    - set_preference: 设定项目偏好/记录约定/记住规则（不是教学解释。如"记住XX放YY"、"以后都用ZZ"、"默认遵循AA规范"）

    目标类型（target_type）：
    - code: 源代码/业务逻辑
    - test: 测试代码
    - config: 配置文件（tsconfig/eslint/vite/prettier/pyproject.toml/.env）
    - infra: 基础设施（Docker/docker-compose/k8s/CI/CD/nginx）
    - file: 纯文本文档（README/LICENSE/Markdown/.env.example）
    - dep: 依赖管理（安装/移除/升级包）
    - none: 无目标（对话/解释/审查/分析）

    置信度（confidence）：0.0 ~ 1.0，你有多确定这个分类正确。

    输出格式（必须严格 JSON）：
    {"intent":"<intent>","target_type":"<target_type>","confidence":<float>,"reasoning":"<一句话推理>"}

    示例：
    用户："帮我写个排序函数"
    输出：{"intent":"write_code","target_type":"code","confidence":0.98,"reasoning":"明确要求编写代码函数"}

    用户："docker-compose.yml 里没配 Redis，你给加一个进去"
    输出：{"intent":"write_code","target_type":"infra","confidence":0.95,"reasoning":"修改docker-compose基础设施配置"}

    用户："怎么优化这个SQL查询"
    输出：{"intent":"explain_code","target_type":"none","confidence":0.85,"reasoning":"请求解释优化方法，未要求实施"}

    用户："项目连个说明都没有，整个README吧"
    输出：{"intent":"write_code","target_type":"file","confidence":0.97,"reasoning":"要求创建README文档文件"}

    用户："把代码里console.log全清掉"
    输出：{"intent":"refactor","target_type":"code","confidence":0.92,"reasoning":"清理调试代码，属于重构操作"}

    用户："运行测试"
    输出：{"intent":"write_code","target_type":"test","confidence":0.97,"reasoning":"要求运行/执行测试，属于工程任务而非项目维护"}

    用户："帮我运行测试并检查代码"
    输出：{"intent":"write_code","target_type":"test","confidence":0.96,"reasoning":"要求执行测试并检查代码，是工程任务"}

    用户："run tests"
    输出：{"intent":"write_code","target_type":"test","confidence":0.97,"reasoning":"要求运行测试，属于代码生成/执行类工程任务"}

    用户："记住，数据加载统一放在 src/ 里"
    输出：{"intent":"set_preference","target_type":"config","confidence":0.95,"reasoning":"要求记住一个项目约定，属于设置偏好"}

    用户："以后都用 pandas 做数据处理吧"
    输出：{"intent":"set_preference","target_type":"config","confidence":0.94,"reasoning":"设定默认技术选型偏好"}

    重要：运行测试、执行测试、run test 属于 write_code 而不是 workspace_maintenance。workspace_maintenance 仅限缩进/格式化/语法检查/环境安装。"记住""以后都""默认用""统一放"这类设定偏好的指令属于 set_preference 而不是 mentor_explain。

    现在分类（只输出 JSON）："""

# =========================================================
# ① 强制工程任务（最高优先级）
# =========================================================
FORCE_WRITE_CODE_PATTERNS = [
    # ---- 明确工程指令 ----
    r"(?:按照|按|根据|基于).{0,24}(?:上面|上文|前面|之前|刚才|上一轮|前述).{0,24}(?:对话|方案|设计|要求|内容|项目)?.{0,16}(?:执行|实现|编写|开发|落地|开始写|动手)",
    r"(?:继续|现在开始|现在).{0,24}(?:帮我)?(?:编写|写代码|实现|开发|创建项目|动手)",
    r"(?:上面|上文|前面|之前|刚才|上一轮|前述|上述).{0,36}(?:的)?(?:内容|对话|方案|设计|要求|项目|架构|代码)?.{0,12}(?:请|帮我|帮忙).{0,8}(?:执行|实现|编写|开发|写|落地|完成|动手)",
    r"(?:请|帮我|帮忙).{0,12}(?:执行|实现|编写|写|开发|落地|完成).{0,24}(?:上面|上文|前面|之前|刚才|上一轮|前述|上述).{0,16}(?:内容|对话|方案|设计|要求|代码|项目|架构)",
    r"(?:根据|按照|基于).{0,36}(?:上述|以上|上面|前述).{0,24}(?:编写|实现|开发|写代码|生成)",

    # ---- 自然对话式工程指令（用户真实表达） ----
    r"(?:很好|好的|OK|okay?|对的|不错|行|可以|好|嗯嗯?|对|是的).{0,12}(?:就按|就照|开始|执行|运行|实现|做吧|来吧|动手|往下|写起)",
    r"(?:继续|往下).{0,8}(?:写|做|执行|实现|开发|进行|干|完成)",
    r"(?:那就|那么|那).{0,8}(?:请|麻烦)?.{0,4}(?:执行|实现|编写|开始|动手|做吧|来吧)",
    r"(?:OK|okay?|好的|行|可以).{0,16}(?:按|按照|照).{0,16}(?:这个|该|上面|前述|之前).{0,16}(?:方案|设计|架构|思路|计划).{0,12}(?:实现|执行|写|开发|编写|动手)",
    r"(?:我们|咱们).{0,8}(?:来|开始).{0,8}(?:实现|做|写|开发|动手|编写)",

    # ---- 修改型工程指令 ----
    r"(?:把|将).{0,8}(?:上面|上文|前面|之前|那个|这个).{0,20}(?:改|换|修改|调整|替换).{0,8}(?:成|为|到|一下)",
    r"(?:把|将).{0,4}(?:\S).{0,20}(?:换成|改成|改为|调整为|替换为)",

    # ---- 极简命令（单/双字） ----
    r"^(?:执行|运行|实现|编译|部署|发布|构建|build|run|deploy)$",

    # ---- 确认继续型 ----
    r"(?:是的|没错|对|正是).{0,8}(?:请|麻烦)?.{0,4}(?:继续|往下|接下去)",

    # ---- 文件写入/操作指令 ----
    r"(?:请|帮我|帮忙|需要|那么).{0,8}(?:写入|添加|新建|创建|补上|补全|生成).{0,24}(?:文件|文档|requirements|README|\.txt|\.md)",
    r"(?:缺少|没有|缺失|需要|补上).{0,200}(?:请|帮我|帮忙|补上|补全|写入).{0,4}(?:写入|添加|创建|生成|写|$)",
    r"(?:写入|请写入|帮写入|补上|补全).{0,12}(?:requirements|README|文档|文件|\.txt|\.md)",
    r"请写入\b|写入.{0,4}(?:文件|文档|requirements)|补上.{0,4}(?:requirements|\.txt|文件|文档|\s*$)",
    r"补上\s*$|补全\s*$",
    r"(?:把|将).{0,4}(?:api|auth|vote|storage|utils|main).{0,4}(?:重命名|改名|改名为|改成|改为|rename)",

    # ---- 原有工程模式（保留） ----
    r"创建.*模块", r"创建.*项目", r"创建.*文件", r"创建.*脚本",
    r"创建一个?.{0,12}(?:函数|算法|类|工具)",
    r"写一个.{0,12}(?:函数|算法|类|工具)",
    r"实现.{0,16}(?:算法|函数|类|脚本)",
    r"实现.{0,16}(?:排序|搜索|查找|遍历)",
    r"(?:新增|添加|增加|扩展).{0,24}(?:功能|模块|支持|能力)",
    r"生成.{0,24}(?:代码|程序|脚本)", r"实现.*功能", r"开发.*功能",
    r"写.{0,16}(?:代码|程序|脚本)", r"编写.{0,16}(?:代码|程序|脚本)", r"写一个.*模块",
    r"build.*module", r"create.*module", r"generate.*code",
    r"implement.*function", r"implement.*module",
    r"implement.*(?:algorithm|search|sort|class)",
    r"(?:add|extend).{0,24}(?:feature|support|module|function)",
    r"write.*script", r"create.*project",
    r"write.*(?:algorithm|function|class)",

    # ---- 专业术语工程模式 ----
    r"(?:生成|创建|编写|新建|写).{0,16}(?:pyproject\.toml|\.env\.example|Dockerfile|docker-compose|nginx|Makefile|\.editorconfig|\.prettierrc|\.eslintrc)",
    r"(?:生成|创建|编写|新建|写).{0,8}(?:env|env示例|环境变量).{0,16}(?:模板|文件|example)",
    r"(?:配置|启用|开启|调整|修改|设置).{0,16}(?:Vite|Webpack|ESLint|Babel|tsconfig|Prettier|proxy|反向代理|CORS|server\.)",
    r"(?:配置|启用|开启).{0,16}(?:strictNullChecks|noUncheckedIndexedAccess|strict|esModuleInterop|noImplicit)",
    r"(?:启用|开启|关闭|调整|修改).{0,16}(?:tsconfig|eslint|prettier|vite).{0,16}(?:配置|规则|选项|规则集)",
    r"(?:在|修改|更新).{0,8}(?:tsconfig|eslint|vite|webpack).{0,8}(?:中|里|里面).{0,4}(?:启用|添加|修改|配置)",

    # ---- 测试生成 ----
    r"(?:编写|写|添加|创建|生成).{0,16}(?:单元测试|集成测试|E2E测试|端到端测试|测试脚本|test|spec|测试用例)",
    r"(?:编写|写|添加|创建|生成).{0,16}(?:Vitest|Jest|Playwright|Cypress|MSW|Mock).{0,8}(?:测试|脚本|配置|拦截|mock)",
    r"使用.{0,8}MSW.{0,16}(?:拦截|mock|模拟|测试)",
    r"(?:为|给|对).{0,16}(?:函数|方法|组件|模块|controller|service).{0,16}(?:编写|写|添加|创建).{0,8}(?:测试|test|spec)",

    # ---- 部署/基础设施 ----
    r"(?:编写|创建|生成|写).{0,8}(?:Dockerfile|docker-compose|k8s|helm|CI|CD|GitHub.{0,8}Actions|GitLab.{0,8}CI)",
    r"(?:分离|实现|编写).{0,16}(?:构建阶段|运行阶段|multi[- ]stage|多阶段)",
    r"(?:基于|使用).{0,8}(?:alpine|debian|ubuntu|node|python).{0,8}(?:镜像|image).{0,8}(?:编写|创建|构建|生成)",

    # ---- 架构重构（抽取/拆分/迁移） ----
    r"(?:抽取|提取|抽象|隔离|分离).{0,24}(?:为|成|到)(?:.{0,8}(?:类|模块|服务|组件|Service|Module|Component))",
    r"(?:拆分|分解|分割).{0,24}(?:为|成)(?:.{0,8}(?:组件|模块|函数|文件|类))",
    r"(?:迁移|切换|升级|替换|转换).{0,8}(?:至|到|为|成).{0,24}(?:Zustand|Redux|MobX|Pinia|Jotai|Recoil|Context)",
    r"(?:引入|应用|采用|实施|集成).{0,8}(?:Repository|Service|Factory|Strategy|Observer|Decorator|依赖注入|IoC).{0,8}(?:模式|层|类|模块)",
    r"(?:重构|重写|改写|改造).{0,24}(?:为|成|至)(?:.{0,8}(?:Promise|async|await|模块|模式|范式))",

    # ---- 代码生成/实现（含专业目标） ----
    r"(?:生成|创建|编写|新建|写|实现).{0,16}(?:模块|项目|组件|接口|类|服务|函数|方法|脚本|配置|规则|代理|路由|中间件)",
    r"(?:实施|执行|落地|动手).{0,16}(?:代码分割|路由分割|懒加载|lazy.{0,8}load|Suspense)",
    r"(?:添加|增加|创建|新建).{0,8}(?:复合索引|索引|migration|migration|数据迁移)",
    r"(?:改写|重写|修改|调整|优化).{0,8}(?:为|成).{0,4}(?:JOIN|批量查询|批量|子查询|CTE|with)",

    # ---- 专业修复/诊断 ----
    r"(?:修复|解决|处理|纠正).{0,16}(?:SSR|水合|Hydration|CORS|跨域|预检|OPTIONS|405|错误|bug|问题|警告)",
    r"(?:修复|解决|处理).{0,24}(?:返回|响应|状态码|StatusCode).{0,4}(?:405|404|500|403|401|429)",
    r"(?:诊断|排查|分析|调查|定位|检查).{0,24}(?:CORS|内存泄漏|性能|瓶颈|错误|bug|问题|崩溃|死锁)",

    # ---- 口语化操作指令 ----
    r"(?:整|弄|加)[个下].{0,16}(?:文件|文档|README|LICENSE|MIT|协议|\.txt|\.md|\.env|\.example|配置|模块)",
    r"(?:撸|搞|造)[个下].{0,16}(?:模块|项目|功能|组件|页面)",
    r"(?:给|帮|为|替).{0,16}(?:写|补充|添加|加|创建|生成).{0,16}(?:README|LICENSE|\.md|\.txt|\.env|文档|文件|协议)",
    r"(?:你|您|帮忙|帮我|替我).{0,4}(?:给|帮).{0,4}(?:加|补|写|添|追加|塞).{0,4}(?:一个|一下|个|进去)",
    r"整理成.{0,12}(?:Markdown|文档|README|README)",
    r".{0,40}(?:换成|改成|改为|替换成|切到|换一下|改一下|改改).{0,20}(?:主题色|颜色|样式|风格|方案|逻辑|密码|配置)",
    r"(?:写死成|硬编码成|写死为).{0,16}(?:test\d+|admin\d*|password\d*|localhost)",
    r"(?:搞|做|加|写)[个下].{0,16}(?:分页|懒加载|缓存|搜索|排序|过滤)",
    r"(?:移除|删除|卸载|拿掉|去掉).{0,12}(?:试试|看看|吧|呗)",

    # ---- 上下文依赖型工程指令 ----
    r"(?:就按|按照|根据).{0,24}(?:昨天|上次|上回|上上个|刚才|之前|前面|咱[们]?)?.{0,16}(?:说的|讨论的|决定的|确认的|规划的|设计的).{0,24}(?:方案|思路|想法|架构|设计|计划).{0,24}(?:执行|实现|写|开发|改|做|动手|落地)",
    r"(?:上次|上回|昨天|刚才).{0,24}(?:不是|说过|讲了|建议|提到|推荐).{0,24}(?:就|现在|那).{0,12}(?:把|将|换|改|写|实现|做)",
    r"用回.{0,12}(?:上[个上].{0,4}(?:版本|版|代码|逻辑|方案|实现))",
    r"(?:把我|将).{0,12}(?:刚才|刚刚|刚).{0,12}(?:发的|发你的|发给你的|给你的|提供的|说的).{0,12}(?:JSON|代码|文件|配置).{0,12}(?:存到|保存到|写到|放入|放进)",
    r"照着.{0,16}(?:模块|代码|文件|项目).{0,16}(?:风格|样式|模式|写法|范式|架构|结构|规范).{0,16}(?:给我|帮我|替我)?.{0,8}(?:写|创建|生成|实现|开发|撸|搞|造).{0,16}(?:一个|个|新).{0,8}(?:模块|项目|功能|组件)",
]

PROJECT_IMPLEMENTATION_PATTERNS = [
    r"(?:设计|规划|design|architect).{0,100}"
    r"(?:系统|平台|应用|项目|system|platform|application|project).{0,100}"
    r"(?:有|包含|配套|覆盖|包括|提供|with|including|full[- ]stack).{0,24}"
    r"(?:前端.{0,16}后端|后端.{0,16}前端|frontend.{0,24}backend|backend.{0,24}frontend|"
    r"网页.{0,24}(?:app|小程序)|(?:app|小程序).{0,24}网页|web.{0,24}mobile)",
    r"(?:全栈|full[- ]stack|前后端|frontend.{0,16}backend|backend.{0,16}frontend)"
    r".{0,100}(?:搭建|创建|生成|开发|实现|编写|落地|build|create|generate|develop|implement|scaffold)",
    r"(?:搭建|创建|生成|开发|实现|编写|落地|build|create|generate|develop|implement|scaffold)"
    r".{0,100}(?:全栈|full[- ]stack|前后端|frontend.{0,16}backend|backend.{0,16}frontend)",
]

READ_ONLY_DESIGN_PATTERNS = [
    r"(?:只|仅|只需|仅需|无需|不用|不要|不需要|不必|不得|禁止).{0,20}"
    r"(?:设计|规划|分析|说明|架构|方案|代码|文件|实现|开发|生成|创建|写入)",
    r"(?:design|architecture|analysis)[^.!?\n]{0,40}"
    r"(?:only|just)[^.!?\n]{0,24}(?:no code|do not implement|don't implement|without code)",
    r"(?:no code|do not implement|don't implement|without code)[^.!?\n]{0,40}"
    r"(?:design|architecture|analysis)",
]

# =========================================================
# ② 普通意图匹配（按优先级）
# =========================================================
INTENT_PATTERNS: Dict[str, list] = {
    "set_preference": [
        r"(?:记住|记下|记录).{0,24}(?:约定|规则|偏好|规范|要求|偏好|配置)",
        r"(?:以后|今后|往后|之后|下回|下次).{0,16}(?:都|一律|统一|默认).{0,24}(?:用|放在|使用|采用|遵循|放在|放到)",
        r"(?:设定|设置|配置).{0,16}(?:偏好|默认|规则|规范|约定)",
        r"(?:统一|一律).{0,16}(?:放在|放到|使用|采用)",
        r"(?:默认|总是).{0,16}(?:使用|采用|放在|放到)",
        r"remember.{0,24}(?:convention|rule|preference|standard)",
        r"(?:set|configure).{0,16}(?:preference|default|rule|standard)",
        r"(?:以后|今后|往后).{0,16}(?:不|别|不要|禁止).{0,16}(?:用|使用|采用|放在|放到)",
        r"(?:就|都).{0,4}(?:按|按照|照).{0,16}(?:这个|这|上面|前述).{0,16}(?:规范|标准|约定|规则).{0,8}(?:来|做|写|实现)",
    ],

    "workspace_maintenance": [
        r"(?:检查|扫描|修复|整理).{0,30}(?:整个项目|所有|全部|项目).{0,30}(?:语法|缩进)",
        r"(?:语法|缩进).{0,30}(?:整个项目|所有|全部|项目)",
        r"(?:修改|修复|检查|整理).{0,24}项目.{0,24}(?:代码|python|源码).{0,16}(?:缩进|语法)",
        r"(?:项目|仓库|代码库).{0,24}(?:代码|python|源码).{0,16}(?:缩进|语法).{0,12}(?:错误|问题)",
        r"检查.{0,20}项目文件",
        r"创建.{0,20}虚拟环境",
        r"安装.{0,20}(?:项目|第三方|python)?(?:依赖|库|包)",
        r"(?:执行|运行|帮我|请|帮忙).{0,12}(?:安装|补装|配置).{0,16}(?:依赖|库|包|pip|fastapi|uvicorn|numpy|pytest|模块)?",
        r"执行安装|帮我安装|请安装|需要补装|需要安装",
        r"(?:pip|pip3)\s+install",
        r"安装.{0,12}(?:fastapi|uvicorn|pytest|numpy|依赖|第三方库)",
        r"(?:缺少|没有|缺失).{0,8}(?:fastapi|uvicorn|pytest).{0,8}(?:安装|补装|装上)",
        r"(?:补装|补上).{0,16}(?:依赖|库|包|fastapi|uvicorn|模块)",
        r"(?:check|scan|fix).{0,30}(?:all|entire|project).{0,30}(?:syntax|indentation)",
        r"(?:create|setup).{0,20}virtual[\s_-]*environment",
        r"install.{0,24}(?:project\s+)?dependenc",
    ],

    "mentor_explain": [
        r"怎么人工测试", r"如何手动测试", r"人工测试流程", r"manual(?:ly)? test",
        r"how.*test.*manually", r"how.*manual.*test",
        r"(?:教我|告诉我|说明).{0,20}(?:如何|怎么).{0,16}(?:使用|运行|启动|操作).{0,20}(?:这个|该|本)?(?:项目|仓库|应用|代码库)",
        r"(?:如何|怎么).{0,16}(?:使用|运行|启动|操作).{0,20}(?:这个|该|本)?(?:项目|仓库|应用|代码库)",
        r"how.{0,16}(?:to use|to run|to start).{0,24}(?:project|repository|application|repo)",
    ],

    "external_git": [
        r"上传.*github", r"推送.*github", r"发布到.*github", r"push.*to.*github",
        r"upload.*to.*github", r"git push"
    ],

    "chat": [
        r"你是谁", r"你是.*谁", r"介绍一下.*自己",
        r"你觉得", r"你怎么看", r"聊聊", r"聊天",
        r"hello", r"hi\b", r"hey\b",
        r"what.*are.*you", r"who.*are.*you", r"what do you think", r"how are you",
        r"你好", r"您好", r"哈喽",
    ],

    "fix_code": [
        r"修复.*(?:错误|bug)", r"解决.*bug", r"报错", r"无法运行", r"运行不了",
        r"语法错误", r"缩进错误", r"syntax[\s_-]*error", r"indentation[\s_-]*error",
        r"fix.*error", r"debug", r"exception", r"crash"
    ],

    "explain_and_fix": [
        r"(?:看看|检查|分析|解释|告诉我).{0,30}(?:错误|报错|异常|bug).{0,30}(?:并|然后|再|同时).{0,20}(?:修复|解决|改好)",
        r"(?:解释|说明).{0,24}(?:错误|报错|异常|bug).{0,24}(?:修复|解决)",
        r"(?:fix|solve).{0,24}(?:error|bug|exception).{0,24}(?:explain|tell me why)",
    ],

    "code_review": [
        r"(?:代码|项目|改动|变更).{0,18}(?:审查|审阅|review)",
        r"(?:审查|审阅|review).{0,24}(?:代码|项目|改动|变更)",
        r"(?:检查|审查|审阅).{0,32}(?:代码质量|代码风险|安全风险|正确性|漏洞|风险)",
        r"(?:看看|检查).{0,18}(?:代码|项目).{0,18}(?:问题|漏洞|风险)",
        r"(?:check|review).{0,24}(?:code quality|security|correctness|risk|vulnerabilit)",
        r"review.{0,24}(?:code|project|changes)",
    ],

    "delete_files": [
        r"(?:删除|移除|清理).{0,24}(?:文件|目录|文件夹|项目|测试文件夹|文件夹|模块)",
        r"(?:delete|remove|trash).{0,32}(?:file|directory|folder|project)",
        r"(?:删除|移除)\s+[`\"']?(?:[\w.@+-]+[\\/])+[\w.@+-]+(?:\.[\w-]+)?",
        r"(?:删除|移除)\s+[`\"']?[\w.@+-]+\.[\w-]+",
        r"(?:delete|remove|trash)\s+[`\"']?(?:[\w.@+-]+[\\/])+[\w.@+-]+(?:\.[\w-]+)?",
        r"(?:delete|remove|trash)\s+[`\"']?[\w.@+-]+\.[\w-]+",
        r"(?:砍掉|干掉|拿掉|删了|删掉).{0,24}(?:文件|目录|文件夹|模块|代码|测试文件夹|项目)",
        r"(?:文件|目录|文件夹|模块|代码|测试文件夹|项目).{0,24}(?:砍掉|干掉|拿掉|删了|删掉)",
        r"(?:删了|删掉|砍掉|干掉)[^。！？\n]*(?:吧|呗|哈|呀|噢|哦|嘛)?[。！？\s]*$",
    ],

    "explain_code": [
        r"解释.*代码", r"说明.*这段", r"理解.*这个",
        r"这是什么意思", r"帮我看看这个函数",
        r"explain.*code", r"what does.*(?:mean|do)"
    ],

    "creative_writing": [
        r"(?:写|作|来|定)(?:一首|首)?.{0,12}诗",
        r"写.*故事", r"写.*散文", r"创作.*文章", r"创作.*故事",
        r"write.*poem", r"write.*story", r"create.*story"
    ],

    "analysis": [
        r"分析.*需求", r"评估.*方案",
        r"analyze.*requirement", r"evaluate.*solution"
    ],

    "architecture": [
        r"设计.*系统", r"架构.*方案", r"架构设计.*(?:系统|平台|应用)",
        r"design.*(?:architecture|system|platform|application)",
        r"(?:system|platform|application).{0,40}(?:architecture|design)",
        r"architecture.*design"
    ],

    "refactor": [
        r"重构.*代码", r"优化.*结构", r"统一.*缩进", r"缩进.*统一", r"格式化.*python",
        r"refactor.*code", r"optimize.*structure", r"format.*python",
        r"(?:抽取|提取|抽象|隔离).{0,8}(?:为|成|到)",
        r"(?:拆分|分解).{0,8}(?:为|成)",
        r"(?:迁移|切换).{0,8}(?:至|到|为)",
        r"(?:引入|采用).{0,8}(?:Repository|Service|Factory|Strategy|Observer|模式)",
        r"(?:清掉|清空|去掉|移除掉|移除一下|换掉|替换掉|改掉).{0,30}(?:console|log|debug|打印|输出|硬编码|依赖|包|模块|import|require)",
        r"(?:全|都|全部|统统).{0,12}(?:清掉|清空|去掉|移除|干掉|拿掉)",
    ],

    "generate_doc": [
        r"生成.*文档", r"写.*注释",
        r"generate.*documentation", r"write.*comments"
    ],
}

# =========================================================
# ③ 意图 → 人格
# =========================================================
INTENT_TO_PERSONA: Dict[str, str] = {
    "chat": "conversational",
    "mentor_explain": "mentor",
    "code_review": "reviewer",
    "delete_files": "file_manager",
    "external_git": "engineer",
    "workspace_maintenance": "engineer",
    "write_code": "engineer",
    "fix_code": "engineer",
    "explain_and_fix": "engineer",
    "explain_code": "engineer",
    "creative_writing": "creator",
    "analysis": "engineer",
    "architecture": "architect",
    "refactor": "engineer",
    "generate_doc": "engineer",
    "set_preference": "engineer",
}

# =========================================================
# ⭐ v4.0: ExecutionProfile — LLM 无需在 analyze 阶段输出
# =========================================================
class ExecutionProfile:
    __slots__ = (
        "output_mode", "workspace_dependency", "target_format",
        "requires_fileops", "requires_workspace_scan",
        "requires_test", "estimated_complexity",
    )

    def __init__(
        self,
        output_mode: str = "code",
        workspace_dependency: str = "rw",
        target_format: str = "plain_text",
        requires_fileops: bool = True,
        requires_workspace_scan: bool = True,
        requires_test: bool = False,
        estimated_complexity: str = "moderate",
    ):
        self.output_mode = output_mode
        self.workspace_dependency = workspace_dependency
        self.target_format = target_format
        self.requires_fileops = requires_fileops
        self.requires_workspace_scan = requires_workspace_scan
        self.requires_test = requires_test
        self.estimated_complexity = estimated_complexity

    def as_dict(self) -> Dict:
        return {
            "output_mode": self.output_mode,
            "workspace_dependency": self.workspace_dependency,
            "target_format": self.target_format,
            "requires_fileops": self.requires_fileops,
            "requires_workspace_scan": self.requires_workspace_scan,
            "requires_test": self.requires_test,
            "estimated_complexity": self.estimated_complexity,
        }

# 意图 → 默认 ExecutionProfile（无 skill 匹配时的兜底）
_INTENT_DEFAULT_PROFILE: Dict[str, dict] = {
    "chat":              dict(output_mode="text", ws_dep="none", fileops=False, scan=False, test=False, fmt="plain_text", complexity="simple"),
    "mentor_explain":    dict(output_mode="text", ws_dep="none", fileops=False, scan=False, test=False, fmt="plain_text", complexity="simple"),
    "code_review":       dict(output_mode="text", ws_dep="read_only", fileops=False, scan=True, test=False, fmt="plain_text", complexity="simple"),
    "delete_files":      dict(output_mode="code", ws_dep="rw", fileops=True, scan=True, test=False, fmt="plain_text", complexity="moderate"),
    "external_git":      dict(output_mode="mixed", ws_dep="rw", fileops=True, scan=True, test=False, fmt="plain_text", complexity="moderate"),
    "workspace_maintenance": dict(output_mode="code", ws_dep="rw", fileops=True, scan=True, test=False, fmt="plain_text", complexity="moderate"),
    "write_code":        dict(output_mode="code", ws_dep="rw", fileops=True, scan=True, test=True, fmt="py", complexity="moderate"),
    "fix_code":          dict(output_mode="code", ws_dep="rw", fileops=True, scan=True, test=True, fmt="py", complexity="moderate"),
    "explain_and_fix":   dict(output_mode="code", ws_dep="rw", fileops=True, scan=True, test=True, fmt="py", complexity="moderate"),
    "explain_code":      dict(output_mode="text", ws_dep="read_only", fileops=False, scan=True, test=False, fmt="plain_text", complexity="simple"),
    "creative_writing":  dict(output_mode="text", ws_dep="none", fileops=False, scan=False, test=False, fmt="plain_text", complexity="simple"),
    "analysis":          dict(output_mode="text", ws_dep="read_only", fileops=False, scan=True, test=False, fmt="plain_text", complexity="moderate"),
    "architecture":      dict(output_mode="document", ws_dep="read_only", fileops=True, scan=True, test=False, fmt="md", complexity="moderate"),
    "refactor":          dict(output_mode="code", ws_dep="rw", fileops=True, scan=True, test=True, fmt="py", complexity="moderate"),
    "generate_doc":      dict(output_mode="document", ws_dep="read_only", fileops=True, scan=True, test=False, fmt="md", complexity="simple"),
    "set_preference":    dict(output_mode="text", ws_dep="read_write", fileops=True, scan=False, test=False, fmt="plain_text", complexity="simple"),
}

# 测试执行请求的正则模式 — 用于硬覆盖 LLM 误判为 workspace_maintenance 的情况
_TEST_EXECUTION_PATTERNS = [
    r"(?:运行|执行|跑).{0,8}(?:测试|test|pytest|unittest)",
    r"(?:run|exec).{0,8}(?:test|pytest|unittest)",
    r"(?:帮我|请).{0,12}(?:运行|执行|跑|run).{0,8}(?:测试|test)",
    r"(?:运行|执行|run).{0,4}(?:单元|集成|e2e|端到端).{0,4}(?:测试|test)",
    r"pytest\b",
    r"(?:npm|yarn|pnpm)\s+(?:run\s+)?test",
    r"python\s+(?:-m\s+)?pytest",
]