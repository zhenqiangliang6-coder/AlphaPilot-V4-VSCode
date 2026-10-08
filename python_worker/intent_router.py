# -*- coding: utf-8 -*-
# intent_router.py — 官方 + 智能增强版（2026）
# ---------------------------------------------------------
# 架构合规性（Architecture Compliance）
#
# ✅ Worker = 真相（Truth Source）
#    - 所有意图判断、人格选择、执行链决策都必须发生在 Worker 内部
#    - 任何前端、扩展、Node API 都不得参与意图判断
#
# ✅ 协议 = 宪法（Protocol = Constitution）
#    - Intent → Persona → Execution Chain 必须遵守统一协议
#    - 执行链必须完整、可预测、可验证
#    - 不允许出现“write 找不到 plan”、“refine 找不到 write”这种断链情况
#
# 本文件是 Worker 的核心智能模块，负责：
# 1. 识别用户意图
# 2. 选择人格
# 3. 从唯一映射中为任务选择最小可用执行链
#
# ---------------------------------------------------------

import re
import json
import os
import concurrent.futures
from typing import Dict, Tuple, List


def _get_env(key: str, default: str = "") -> str:
    """从 worker_config 或环境变量获取配置值"""
    try:
        from worker_config import __dict__ as cfg
        return cfg.get(key, os.environ.get(key, default))
    except Exception:
        return os.environ.get(key, default)


class IntentRouter:
    """
    Intent Router — Worker 内部的智能决策模块
    ---------------------------------------------------------
    设计原则：
    - 明确任务意图优先，未知请求保持只读对话
    - 文档任务优先级最低（generate_doc）
    - creative_writing 不覆盖工程任务
    - 执行链必须完整，不允许断链
    - 所有逻辑必须在 Worker 内部执行（Worker = 真相）
    """

    # =========================================================
    # ⓪ LLM + Regex 联合路由（工业标准）
    # =========================================================
    # 支持的意图全集（LLM 只能输出这些值之一）
    ALL_INTENTS = (
        "chat", "mentor_explain", "code_review", "delete_files",
        "external_git", "workspace_maintenance", "write_code",
        "fix_code", "explain_and_fix", "explain_code",
        "creative_writing", "analysis", "architecture",
        "refactor", "generate_doc",
    )

    # 目标类型（帮助下游精确决策）
    # file  = 纯文件操作（README, LICENSE, .env, Dockerfile, 配置）
    # code  = 源代码/业务逻辑
    # test  = 测试代码
    # config = 配置文件修改（tsconfig, eslint, vite, pyproject.toml）
    # infra = 基础设施（Dockerfile, k8s, CI/CD）
    # dep   = 依赖管理（npm/pip install, 移除/升级包）
    ALL_TARGET_TYPES = ("file", "code", "test", "config", "infra", "dep", "none")

    # LLM 轻量分类提示词 — 仅做意图路由，不跑完整工程链
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

    重要：运行测试、执行测试、run test 属于 write_code 而不是 workspace_maintenance。workspace_maintenance 仅限缩进/格式化/语法检查/环境安装。

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
        # "很好/好的/OK/对的/不错 + 就按/执行/运行/开始/实现/做吧"
        r"(?:很好|好的|OK|okay?|对的|不错|行|可以|好|嗯嗯?|对|是的).{0,12}(?:就按|就照|开始|执行|运行|实现|做吧|来吧|动手|往下|写起)",
        # "继续/往下 + 写/做/执行/实现/开发/进行"
        r"(?:继续|往下).{0,8}(?:写|做|执行|实现|开发|进行|干|完成)",
        # "那就/那就请/那就麻烦 + 执行/实现/编写/开始"
        r"(?:那就|那么|那).{0,8}(?:请|麻烦)?.{0,4}(?:执行|实现|编写|开始|动手|做吧|来吧)",
        # "OK/好的/行 + 按这个方案/设计 + 实现/执行/写"
        r"(?:OK|okay?|好的|行|可以).{0,16}(?:按|按照|照).{0,16}(?:这个|该|上面|前述|之前).{0,16}(?:方案|设计|架构|思路|计划).{0,12}(?:实现|执行|写|开发|编写|动手)",
        # "我们来 + 实现/做/写/开发"
        r"(?:我们|咱们).{0,8}(?:来|开始).{0,8}(?:实现|做|写|开发|动手|编写)",

        # ---- 修改型工程指令 ----
        # "把上面那个X改成Y"
        r"(?:把|将).{0,8}(?:上面|上文|前面|之前|那个|这个).{0,20}(?:改|换|修改|调整|替换).{0,8}(?:成|为|到|一下)",
        # "把X换成/改成Y"
        r"(?:把|将).{0,4}(?:\S).{0,20}(?:换成|改成|改为|调整为|替换为)",

        # ---- 极简命令（单/双字） ----
        r"^(?:执行|运行|实现|编译|部署|发布|构建|build|run|deploy)$",

        # ---- 确认继续型 ----
        # "是的，请继续" / "对，继续" / "没错，继续做"
        r"(?:是的|没错|对|正是).{0,8}(?:请|麻烦)?.{0,4}(?:继续|往下|接下去)",

        # ---- 文件写入/操作指令（"请写入", "添加文件", "写requirements"） ----
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

        # ================================================================
        # 专业术语工程模式（"抽取为" "迁移至" "配置Vite" "编写单元测试" 等）
        # ================================================================
        # ---- 配置生成 / 配置修改 ----
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

        # ---- 口语化操作指令（"整个""弄个""加个""撸一个""搞个""删了吧""干掉"等） ----
        # 口语化文件创建
        r"(?:整|弄|加)[个下].{0,16}(?:文件|文档|README|LICENSE|MIT|协议|\.txt|\.md|\.env|\.example|配置|模块)",
        r"(?:撸|搞|造)[个下].{0,16}(?:模块|项目|功能|组件|页面)",
        r"(?:给|帮|为|替).{0,16}(?:写|补充|添加|加|创建|生成).{0,16}(?:README|LICENSE|\.md|\.txt|\.env|文档|文件|协议)",
        # "你给加一个进去" / "你帮我补一个" / "给加一个"
        r"(?:你|您|帮忙|帮我|替我).{0,4}(?:给|帮).{0,4}(?:加|补|写|添|追加|塞).{0,4}(?:一个|一下|个|进去)",
        # "整理成 Markdown/文档"
        r"整理成.{0,12}(?:Markdown|文档|README|README)",
        # "换成/改一下" 无"把"前缀
        r".{0,40}(?:换成|改成|改为|替换成|切到|换一下|改一下|改改).{0,20}(?:主题色|颜色|样式|风格|方案|逻辑|密码|配置)",
        r"(?:写死成|硬编码成|写死为).{0,16}(?:test\d+|admin\d*|password\d*|localhost)",
        # 口语化功能实现
        r"(?:搞|做|加|写)[个下].{0,16}(?:分页|懒加载|缓存|搜索|排序|过滤)",
        # "移除掉试试" / "删掉试试" / "卸载看看" — 依赖/包管理
        r"(?:移除|删除|卸载|拿掉|去掉).{0,12}(?:试试|看看|吧|呗)",

        # ---- 上下文依赖型工程指令（依赖记忆注入，但意图明确是工程任务） ----
        # "就按咱们昨天说的方案..."
        r"(?:就按|按照|根据).{0,24}(?:昨天|上次|上回|上上个|刚才|之前|前面|咱[们]?)?.{0,16}(?:说的|讨论的|决定的|确认的|规划的|设计的).{0,24}(?:方案|思路|想法|架构|设计|计划).{0,24}(?:执行|实现|写|开发|改|做|动手|落地)",
        # "上次你不是建议用 dayjs 吗？现在就把 moment 换了吧"
        r"(?:上次|上回|昨天|刚才).{0,24}(?:不是|说过|讲了|建议|提到|推荐).{0,24}(?:就|现在|那).{0,12}(?:把|将|换|改|写|实现|做)",
        # "用回上上个版本"
        r"用回.{0,12}(?:上[个上].{0,4}(?:版本|版|代码|逻辑|方案|实现))",
        # "把我刚才发你的那段 JSON 存到..."
        r"(?:把我|将).{0,12}(?:刚才|刚刚|刚).{0,12}(?:发的|发你的|发给你的|给你的|提供的|说的).{0,12}(?:JSON|代码|文件|配置).{0,12}(?:存到|保存到|写到|放入|放进)",
        # "照着 auth 模块的风格，再给我撸一个订单模块出来"
        r"照着.{0,16}(?:模块|代码|文件|项目).{0,16}(?:风格|样式|模式|写法|范式|架构|结构|规范).{0,16}(?:给我|帮我|替我)?.{0,8}(?:写|创建|生成|实现|开发|撸|搞|造).{0,16}(?:一个|个|新).{0,8}(?:模块|项目|功能|组件)",
    ]

    # Architecture wording combined with concrete full-stack/multi-client
    # deliverables is an implementation request, even when phrased as design.
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
    INTENT_PATTERNS = {
        "workspace_maintenance": [
            r"(?:检查|扫描|修复|整理).{0,30}(?:整个项目|所有|全部|项目).{0,30}(?:语法|缩进)",
            r"(?:语法|缩进).{0,30}(?:整个项目|所有|全部|项目)",
            r"(?:修改|修复|检查|整理).{0,24}项目.{0,24}(?:代码|python|源码).{0,16}(?:缩进|语法)",
            r"(?:项目|仓库|代码库).{0,24}(?:代码|python|源码).{0,16}(?:缩进|语法).{0,12}(?:错误|问题)",
            r"检查.{0,20}项目文件",
            r"创建.{0,20}虚拟环境",
            r"安装.{0,20}(?:项目|第三方|python)?(?:依赖|库|包)",
            # ---- pip install / 执行安装 / 补装 指令 ----
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

        # ⭐ 对话/问答意图（高优先级，避免误判为代码生成）
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
            # ---- 口语化删除（严格限定为文件/目录/模块等实体） ----
            # "干掉" / "删了" 后跟文件类目标
            r"(?:砍掉|干掉|拿掉|删了|删掉).{0,24}(?:文件|目录|文件夹|模块|代码|测试文件夹|项目)",
            # 文件类目标在 "干掉" / "删了" 之前
            r"(?:文件|目录|文件夹|模块|代码|测试文件夹|项目).{0,24}(?:砍掉|干掉|拿掉|删了|删掉)",
            # 句尾口语化删除（容纳中文标点）
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
            # ---- 专业架构重构 ----
            r"(?:抽取|提取|抽象|隔离).{0,8}(?:为|成|到)",
            r"(?:拆分|分解).{0,8}(?:为|成)",
            r"(?:迁移|切换).{0,8}(?:至|到|为)",
            r"(?:引入|采用).{0,8}(?:Repository|Service|Factory|Strategy|Observer|模式)",
            # ---- 口语化重构/清理 ----
            r"(?:清掉|清空|去掉|移除掉|移除一下|换掉|替换掉|改掉).{0,30}(?:console|log|debug|打印|输出|硬编码|依赖|包|模块|import|require)",
            r"(?:全|都|全部|统统).{0,12}(?:清掉|清空|去掉|移除|干掉|拿掉)",
        ],

        # ⭐ generate_doc 放在最低优先级
        "generate_doc": [
            r"生成.*文档", r"写.*注释",
            r"generate.*documentation", r"write.*comments"
        ],
    }

    # =========================================================
    # ③ 意图 → 人格
    # =========================================================
    INTENT_TO_PERSONA = {
        "chat": "conversational",  # ⭐ 对话人格
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
    }

    # =========================================================
    # ④ 意图 → 执行链（Execution Chain）
    # =========================================================
    INTENT_TO_CHAIN = {
        "chat": ["analyze", "plan", "respond"],
        "mentor_explain": ["analyze", "plan", "respond"],
        "code_review": ["analyze", "plan", "respond"],
        "delete_files": ["analyze", "plan", "write"],
        "external_git": ["analyze", "plan"],
        "workspace_maintenance": ["analyze", "fix", "workspace"],
        "write_code": ["analyze", "plan", "write", "workspace", "refine", "test", "fix", "doc", "docstring"],
        "fix_code": ["analyze", "fix", "test"],
        "explain_and_fix": ["analyze", "plan", "fix", "test", "respond"],
        "explain_code": ["analyze", "plan", "respond"],
        "creative_writing": ["analyze", "plan", "write", "refine"],
        "analysis": ["analyze", "plan", "respond"],
        "architecture": ["analyze", "plan", "write"],
        "refactor": ["analyze", "plan", "write", "refine", "test"],
        "generate_doc": ["analyze", "plan", "write", "doc"],
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

    @classmethod
    def _is_test_execution_request(cls, prompt: str) -> bool:
        """检查 prompt 是否明确要求运行/执行测试（而非仅检查语法或编写测试）"""
        prompt_lower = prompt.lower().strip()
        for pattern in cls._TEST_EXECUTION_PATTERNS:
            if re.search(pattern, prompt_lower):
                return True
        return False

    @classmethod
    def execution_chain_for(cls, intent: str, worker: str = "qwen", prompt: str = "") -> List[str]:
        """Select the canonical intent chain, adapting only to a worker's capabilities."""
        chain = list(cls.INTENT_TO_CHAIN.get(intent, cls.INTENT_TO_CHAIN["chat"]))

        if worker == "local":
            chain = ["write"]
        elif worker != "qwen":
            if "workspace" in chain:
                chain = ["analyze", "plan"]
            else:
                chain = ["write" if step == "respond" else step for step in chain]

        prompt_lower = (prompt or "").lower()
        if intent in {"write_code", "refactor"}:
            if re.search(r"(?:文档|说明文档|documentation|readme)", prompt_lower):
                if "doc" not in chain:
                    chain.append("doc")
            if re.search(r"(?:docstring|文档字符串)", prompt_lower):
                if "docstring" not in chain:
                    chain.append("docstring")
            if re.search(r"(?:性能|profile|profiling|性能分析)", prompt_lower):
                if "profile" not in chain:
                    chain.append("profile")
        return chain

    # =========================================================
    # ⓪ LLM 语义分类（LLM + Regex 联合路由第一层）
    # =========================================================
    @classmethod
    def _llm_classify(cls, prompt: str, model_name: str = "qwen") -> Dict:
        """调用对应 Worker 的 LLM 做轻量意图分类，失败返回 None 降级 Regex"""
        try:
            full_prompt = cls.LITE_CLASSIFY_PROMPT + "\n用户：" + prompt
            result_text = cls._call_provider_for_classify(full_prompt, model_name, max_timeout=10)
            if not result_text:
                return None

            json_text = result_text.strip()
            if json_text.startswith("```"):
                json_text = json_text.split("```")[1]
                if json_text.startswith("json"):
                    json_text = json_text[4:]
                json_text = json_text.strip()

            parsed = json.loads(json_text)
            intent = parsed.get("intent", "")
            target_type = parsed.get("target_type", "none")
            confidence = float(parsed.get("confidence", 0))

            if intent not in cls.ALL_INTENTS:
                return None
            if target_type not in cls.ALL_TARGET_TYPES:
                target_type = "none"

            return {
                "intent": intent,
                "target_type": target_type,
                "confidence": confidence,
                "reasoning": parsed.get("reasoning", ""),
            }
        except Exception:
            return None

    @classmethod
    def _get_provider_config(cls, model_name: str) -> Dict:
        """根据 model_name 返回对应 Provider 的 API 配置"""
        model_lower = (model_name or "").lower()

        configs = {
            "qwen": {
                "url": "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation",
                "model": "qwen-turbo",
                "auth_key": "DASHSCOPE_API_KEY",
                "format": "dashscope",
            },
            "gemini": {
                "url": lambda: f"{_get_env('GEMINI_PROXY_URL', 'http://localhost:8000')}/gemini/v1beta/models/{_get_env('GEMINI_MODEL', 'gemini-3.5-flash')}:generateContent",
                "model": lambda: _get_env("GEMINI_MODEL", "gemini-3.5-flash"),
                "auth_key": None,
                "format": "gemini",
            },
            "modelscope": {
                "url": "https://api-inference.modelscope.cn/v1/chat/completions",
                "model": lambda: _get_env("MODELSCOPE_MODEL", "Qwen/Qwen3.8-Flash-Next"),
                "auth_key": "MODELSCOPE_API_KEY",
                "format": "openai",
            },
            "maas": {
                "url": lambda: (_get_env("TENCENT_MAAS_BASE_URL", _get_env("MAAS_URL", "https://tokenhub.tencentmaas.com/v1")).rstrip("/") + "/chat/completions"),
                "model": lambda: _get_env("TENCENT_MAAS_MODEL", "default"),
                "auth_key": "TENCENT_MAAS_API_KEY",
                "alt_auth_key": "TENCENT_MaaS_API_KEY",
                "format": "openai",
            },
            "local": {
                "url": lambda: (_get_env("LOCAL_LLM_BASE_URL", "http://localhost:1234/v1").rstrip("/") + "/chat/completions"),
                "model": lambda: _get_env("LOCAL_LLM_MODEL", "local-model"),
                "auth_key": None,
                "format": "openai",
            },
        }
        return configs.get(model_lower, configs["qwen"])

    @classmethod
    def _call_provider_for_classify(cls, prompt: str, model_name: str, max_timeout: int = 5) -> str:
        """根据 Worker 类型调用对应 LLM 做意图分类"""
        import requests
        cfg = cls._get_provider_config(model_name)

        api_format = cfg.get("format", "openai")
        model = cfg["model"]() if callable(cfg["model"]) else cfg["model"]
        url = cfg["url"]() if callable(cfg["url"]) else cfg["url"]

        auth_key = None
        if cfg.get("auth_key"):
            auth_key = _get_env(cfg["auth_key"], "")
        if not auth_key and cfg.get("alt_auth_key"):
            auth_key = _get_env(cfg["alt_auth_key"], "")

        try:
            if api_format == "dashscope":
                if not auth_key:
                    return ""
                headers = {"Authorization": f"Bearer {auth_key}", "Content-Type": "application/json"}
                body = {
                    "model": model,
                    "input": {"prompt": prompt},
                    "parameters": {"temperature": 0, "result_format": "message", "max_tokens": 120},
                }
                r = requests.post(url, headers=headers, json=body, timeout=max_timeout)
                r.raise_for_status()
                data = r.json()
                output = data.get("output", {})
                if "choices" in output:
                    choices = output.get("choices", [])
                    if choices and isinstance(choices, list):
                        return choices[0].get("message", {}).get("content", "")
                return output.get("text", "")

            elif api_format == "gemini":
                headers = {"Content-Type": "application/json"}
                body = {
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0, "maxOutputTokens": 512},
                    "thinkingConfig": {"thinkingBudget": 0},
                }
                r = requests.post(url, headers=headers, json=body, timeout=max_timeout)
                r.raise_for_status()
                data = r.json()
                candidates = data.get("candidates", [])
                if candidates:
                    content = candidates[0].get("content", {}) or {}
                    parts = content.get("parts", [])
                    if parts:
                        return parts[0].get("text", "")
                return ""

            elif api_format == "openai":
                if auth_key:
                    headers = {"Authorization": f"Bearer {auth_key}", "Content-Type": "application/json"}
                else:
                    headers = {"Content-Type": "application/json"}
                body = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You are an intent classifier. Return only JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0,
                    "max_tokens": 120,
                }
                r = requests.post(url, headers=headers, json=body, timeout=max_timeout)
                r.raise_for_status()
                data = r.json()
                choices = data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
                return ""

        except Exception:
            return ""

    @classmethod
    def detect_intent(cls, prompt: str, model_name: str = "qwen") -> Tuple[str, str, List[str]]:
        """
        智能增强版意图识别（符合架构信条）
        ---------------------------------------------------------
        参数:
            prompt: 用户输入文本
            model_name: Worker 类型 (qwen/gemini/modelscope/maas/local)
                       决定使用哪个 LLM 做语义分类；无对应 API Key 时自动降级 Regex
        Worker = 真相：
            - 所有意图判断必须在 Worker 内部执行
            - 每个 Worker 使用自己的 LLM 做语义分类
        协议 = 宪法：
            - 执行链必须完整、可预测、可验证
        """

        if not prompt or not prompt.strip():
            intent = "chat"
            return intent, cls.INTENT_TO_PERSONA[intent], cls.execution_chain_for(intent)

        # ============================================================
        # ⓪ LLM 语义路由（第一层）— LLM + Regex 联合路由
        #    高置信 → 直接采用；低置信/失败 → 降级到 Regex 兜底
        #    每个 Worker 使用自己的 LLM (model_name 决定)
        # ============================================================
        llm_result = cls._llm_classify(prompt, model_name)
        if llm_result and llm_result["confidence"] >= 0.75:
            intent = llm_result["intent"]
            target_type = llm_result["target_type"]
            confidence = llm_result["confidence"]
            reasoning = llm_result["reasoning"]

            # 硬覆盖：LLM 误将测试执行请求分类为 workspace_maintenance 时，强制修正为 write_code
            # write_code 的执行链包含 test 步骤，能真正执行测试
            if intent == "workspace_maintenance" and cls._is_test_execution_request(prompt):
                intent = "write_code"
                target_type = "test"
                print(f"\n🔧 Intent Router 硬覆盖：测试执行请求不应归类为 workspace_maintenance → write_code")

            persona = cls.INTENT_TO_PERSONA.get(intent, "engineer")
            chain = cls.execution_chain_for(intent, prompt=prompt)

            print(f"\n🧠 Intent Router（{model_name.upper()} 语义路由 | confidence={confidence:.2f}）:")
            print(f"  意图: {intent} | 目标类型: {target_type}")
            print(f"  人格: {persona} | 推理: {reasoning}")
            print(f"  执行链: {' → '.join(chain)}")
            return intent, persona, chain

        # LLM 失败或低置信 → 降级到 Regex 兜底
        if llm_result:
            print(f"\n⚠️ Intent Router（LLM低置信={llm_result['confidence']:.2f}，降级Regex）")
        else:
            print(f"\n⚠️ Intent Router（LLM不可用，降级Regex）")

        prompt_lower = prompt.lower().strip()
        # prompt_stripped 保留原始大小写，配合 re.IGNORECASE 使用
        # 这样开发者写 OK/Build/Run 等大写模式也能正常匹配
        prompt_stripped = prompt.strip()

        # Workspace tool requests must be recognized before the broad create-project
        # patterns, which can also match the word "project" in a dependency clause.
        for pattern in cls.INTENT_PATTERNS["workspace_maintenance"]:
            if re.search(pattern, prompt_lower):
                intent = "workspace_maintenance"
                persona = cls.INTENT_TO_PERSONA[intent]
                chain = cls.execution_chain_for(intent, prompt=prompt)
                print("\n🧠 Intent Router（工作区工具任务识别）:")
                print(f"  意图: {intent}")
                print(f"  人格: {persona}")
                print(f"  执行链: {' → '.join(chain)}")
                return intent, persona, chain

        for intent in ("explain_and_fix", "code_review", "delete_files"):
            if any(re.search(pattern, prompt_lower) for pattern in cls.INTENT_PATTERNS[intent]):
                persona = cls.INTENT_TO_PERSONA[intent]
                chain = cls.execution_chain_for(intent, prompt=prompt)
                print("\n🧠 Intent Router（复合任务识别）:")
                print(f"  意图: {intent}")
                print(f"  人格: {persona}")
                print(f"  执行链: {' → '.join(chain)}")
                return intent, persona, chain

        # =========================================================
        # ① 强制工程任务（最高优先级）
        # =========================================================
        explicitly_read_only_design = (
            any(
                re.search(pattern, prompt_stripped, re.IGNORECASE)
                for pattern in cls.READ_ONLY_DESIGN_PATTERNS
            )
            and any(
                re.search(pattern, prompt_stripped, re.IGNORECASE)
                for pattern in cls.INTENT_PATTERNS["architecture"]
            )
        )
        if not explicitly_read_only_design:
            for pattern in cls.FORCE_WRITE_CODE_PATTERNS:
                if re.search(pattern, prompt_stripped, re.IGNORECASE):
                    intent = "write_code"
                    persona = cls.INTENT_TO_PERSONA[intent]
                    chain = cls.execution_chain_for(intent, prompt=prompt)

                    print("\n🧠 Intent Router（强制工程任务识别）:")
                    print(f"  意图: {intent}")
                    print(f"  人格: {persona}")
                    print(f"  执行链: {' → '.join(chain)}")

                    return intent, persona, chain

        # Do not turn explicitly read-only design/analysis requests into file
        # changes. Otherwise, full-stack and multi-client deliverables need the
        # engineer route so the host can request approval before writing.
        if not explicitly_read_only_design and any(
            re.search(pattern, prompt_stripped, re.IGNORECASE)
            for pattern in cls.PROJECT_IMPLEMENTATION_PATTERNS
        ):
            intent = "write_code"
            persona = cls.INTENT_TO_PERSONA[intent]
            chain = cls.execution_chain_for(intent, prompt=prompt)

            print("\n🧠 Intent Router（全栈项目交付识别）:")
            print(f"  意图: {intent}")
            print(f"  人格: {persona}")
            print(f"  执行链: {' → '.join(chain)}")

            return intent, persona, chain

        # =========================================================
        # ② 普通意图匹配（按优先级）
        # =========================================================
        # 测试执行请求在 Regex 兜底路径中也应正确路由
        if cls._is_test_execution_request(prompt):
            intent = "write_code"
            persona = cls.INTENT_TO_PERSONA[intent]
            chain = cls.execution_chain_for(intent, prompt=prompt)
            print("\n🧠 Intent Router（Regex 测试执行识别）:")
            print(f"  意图: {intent}")
            print(f"  人格: {persona}")
            print(f"  执行链: {' → '.join(chain)}")
            return intent, persona, chain

        for intent, patterns in cls.INTENT_PATTERNS.items():
            if intent == "workspace_maintenance":
                continue
            for pattern in patterns:
                if re.search(pattern, prompt_lower):
                    persona = cls.INTENT_TO_PERSONA[intent]
                    chain = cls.execution_chain_for(intent, prompt=prompt)

                    print("\n🧠 Intent Router 识别结果:")
                    print(f"  意图: {intent}")
                    print(f"  人格: {persona}")
                    print(f"  执行链: {' → '.join(chain)}")

                    return intent, persona, chain

        # =========================================================
        # ③ 默认：工程任务（完整链路）
        # =========================================================
        print("\n⚠️ Intent Router 未识别明确意图，使用安全的对话链路")
        intent = "chat"
        return intent, cls.INTENT_TO_PERSONA[intent], cls.execution_chain_for(intent, prompt=prompt)

    @classmethod
    def plan_request(
        cls,
        prompt: str,
        workspace_available: bool = False,
        source_files_available: bool = False,
        worker: str = "qwen",
        detected_intent: str = None,
        detected_persona: str = None,
        detected_chain: list = None,
    ) -> Dict:
        if detected_intent and detected_persona and detected_chain is not None:
            intent, persona, chain = detected_intent, detected_persona, list(detected_chain)
        else:
            intent, persona, chain = cls.detect_intent(prompt, model_name=worker)
        chain = cls.execution_chain_for(intent, worker=worker, prompt=prompt)

        if intent in {"mentor_explain", "explain_code", "chat"}:
            mode = "MENTOR_EXPLAIN"
            context_requirements = (
                ["README", "tests", "startup scripts"]
                if intent == "mentor_explain"
                else ["user-provided code or error context"]
            )
            capabilities = [
                {"id": "workspace.read", "available": workspace_available},
                {"id": "qwen.explain", "available": True},
            ]
            side_effects = []
            approval = {"required": False, "before": []}
            validation = ["Do not claim tests or commands were executed"]
            recovery = ["Explain missing project context and provide a general procedure"]
        elif intent == "code_review":
            mode = "REVIEW_ONLY"
            context_requirements = ["requested source files", "related project instructions"]
            capabilities = [
                {"id": "workspace.read", "available": workspace_available or source_files_available},
                {"id": "qwen.review", "available": True},
            ]
            side_effects = []
            approval = {"required": False, "before": []}
            validation = ["Return findings only; do not create or modify files"]
            recovery = ["State clearly when requested source files are unavailable"]
        elif intent == "delete_files":
            mode = "FILE_DELETE_PROPOSAL"
            context_requirements = ["explicit workspace-relative target paths"]
            capabilities = [
                {"id": "workspace.read", "available": workspace_available},
                {"id": "fileops.delete.propose", "available": True},
            ]
            side_effects = ["propose deletion candidates; host applies recycle-bin and confirmation policy"]
            approval = {"required": True, "before": ["batch or directory deletion"]}
            validation = [
                "Propose only explicitly named relative paths",
                "Never delete sensitive paths or execute filesystem commands",
            ]
            recovery = ["Ask for exact relative paths when a target is ambiguous"]
        elif intent == "workspace_maintenance":
            mode = "WORKSPACE_MAINTENANCE"
            context_requirements = ["Project source inventory", "syntax and indentation diagnostics", "dependency manifests"]
            capabilities = [
                {"id": "workspace.read", "available": workspace_available},
                {"id": "workspace.environment", "available": workspace_available and worker == "qwen"},
                {"id": "workspace.syntax", "available": workspace_available},
            ]
            side_effects = (
                ["in-scope source changes", "project virtual environment", "declared dependency installation"]
                if worker == "qwen"
                else []
            )
            approval = {"required": False, "before": []}
            validation = ["Compile the language payload and report results", "Report the actual environment and dependency command results"]
            recovery = ["Keep failed operations explicit and do not claim they completed"]
            if worker != "qwen":
                recovery.append("This Worker does not provide the workspace maintenance tool; do not claim a scan or environment operation")
        elif intent == "external_git":
            mode = "EXTERNAL_CAPABILITY"
            context_requirements = ["git status", "branch", "remote", ".gitignore"]
            capabilities = [
                {"id": "git.inspect", "available": False},
                {"id": "git.push", "available": False},
            ]
            side_effects = ["git add", "git commit", "git push"]
            approval = {"required": True, "before": side_effects}
            validation = ["Verify remote and push result after execution"]
            recovery = ["Stop without changing the repository when Git capability is unavailable"]
        else:
            mode = "ENGINEER_EXECUTE"
            if intent in {"fix_code", "explain_and_fix"}:
                context_requirements = ["named source files", "reported error", "related tests"]
            else:
                context_requirements = ["target files", "related tests", "project instructions"]
            capabilities = [
                {"id": "qwen.analyze", "available": True},
                {"id": "qwen.generate_changes", "available": True},
                {"id": "workspace.read", "available": source_files_available or workspace_available},
                {"id": "fileops.apply", "available": True},
                {"id": "project.test", "available": False},
            ]
            side_effects = ["workspace file changes"]
            approval = {"required": True, "before": side_effects + ["project tests"]}
            validation = ["Run relevant project tests after approval"]
            recovery = ["Preserve the proposed changes and report failed validation"]

        return {
            "mode": mode,
            "intent": intent,
            "persona": persona,
            "context_requirements": context_requirements,
            "capabilities": capabilities,
            "execution_chain": list(chain),
            "side_effects": side_effects,
            "approval": approval,
            "validation": validation,
            "recovery": recovery,
        }

    @classmethod
    def get_persona_config(cls, persona_type: str) -> Dict:
        from .agents.qwen.personas import get_persona_config
        return get_persona_config(persona_type)


def detect_user_intent(prompt: str, model_name: str = "qwen") -> Tuple[str, str, List[str]]:
    return IntentRouter.detect_intent(prompt, model_name)


def requires_authorization_before_step(execution_plan: Dict, step_type: str) -> bool:
    return bool(execution_plan.get("approval", {}).get("required")) and step_type == "test"