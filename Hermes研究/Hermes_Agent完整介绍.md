# Hermes Agent：特色机制介绍

> 核查日期：2026-08-03  
> 研究对象：Nous Research开源的Hermes Agent，不是Hermes 3/4模型。  
> 表述边界：“特色”表示Hermes重点整合、实现或产品化的机制，不表示这些思想均由Hermes首创或只有Hermes具备。

## 一、定位

Hermes Agent是Nous Research开源的通用Agent运行时。它允许LLM调用终端、文件、浏览器、Web、记忆、Skill、定时任务和子Agent，并可从CLI、IDE、HTTP API及多个消息平台使用。

普通Agent基础循环可以简化为：

```text
用户请求
  ↓
模型判断下一步
  ├─ 需要工具 → 执行工具 → 返回结果 → 模型继续判断
  └─ 不需要工具 → 输出最终答案
```

Hermes也建立在这个循环之上。它更值得关注的不是基础tool calling，而是围绕长期运行Agent建立的几组机制：

1. Memory、Skill和SessionDB构成的分层长期状态；
2. 规则触发与LLM复盘结合的在线自我改进；
3. Skill的自主创建、修补、整理和人工审批；
4. Curator对持续增长知识库的治理；
5. 同一Agent跨CLI、服务器、消息平台和IDE运行；
6. 主模型、辅助模型、工具后端和执行环境可以独立路由。

## 二、最核心的特色：闭环式自我改进

Hermes所说的“self-improving”通常不表示在线更新模型参数，而是让Agent把经验写入外部、可持久化的状态：

```text
执行真实任务
  ↓
观察成功、失败和用户纠正
  ↓
后台或前台进行语义复盘
  ↓
提炼成Memory或Skill
  ↓
未来会话重新加载
  ↓
改变下一次任务的执行方式
```

底层模型可以完全不变，但下一次执行获得了新的事实、流程和注意事项，因此整体Agent表现可能改善。

### 2.1 两种学习产物

Hermes把经验分成两类：

| 产物 | 保存什么 | 加载方式 | 例子 |
|---|---|---|---|
| Memory | 简短、耐久的事实和偏好 | 通常进入每次会话上下文 | 用户使用Windows；项目采用pytest |
| Skill | 完成一类任务的方法 | 相关时按需加载 | Windows下的安全发布流程；pytest故障诊断步骤 |

这种区分解决了一个实际问题：如果把所有经验都塞进常驻Memory，system prompt会不断膨胀；如果所有经验都只放进历史会话，又很难稳定复用。

Hermes采用：

```text
短小事实 → Memory
较长程序 → Skill
完整历史 → SessionDB
```

### 2.2 自我改进有两条触发路径

#### 路径A：主Agent主动学习

Hermes的系统指导要求主Agent在以下情况考虑调用`skill_manage`：

- 完成复杂任务；
- 经历错误或死路后找到正确方法；
- 用户纠正了工作流程；
- 发现非平凡、可复用的技术；
- 使用中的Skill过时、错误或缺少步骤。

例如，部署Skill给出旧命令，Agent在真实执行中发现新命令并验证成功，可以立即patch原Skill。

#### 路径B：规则触发后台复盘

Hermes运行时还维护计数器。Skill复盘主要按工具迭代数触发，默认配置为：

```yaml
skills:
  creation_nudge_interval: 10
```

达到阈值不等于自动创建Skill，而是启动一次复盘：

```text
工具迭代达到阈值
  ↓
主回答先交付给用户
  ↓
后台Review Agent读取会话快照
  ↓
LLM判断有没有值得沉淀的经验
  ├─ 有 → patch/create/write_file
  └─ 无 → Nothing to save
```

所以它是混合机制：

```text
确定性规则决定“何时复盘”
LLM语义判断决定“学到什么”
权限配置决定“能否写入”
```

### 2.3 后台Review关注什么

当前官方Review提示重点寻找：

- 用户纠正了风格、格式、篇幅或工作方法；
- 用户纠正了步骤顺序或技术路线；
- 出现可复用的修复、绕过方案或调试路径；
- 已加载Skill被证明错误、缺失或过时；
- 用户明确要求记住某种做法。

它也明确排除：

- 一次性网络错误；
- 缺少依赖、凭据未配置等暂时环境状态；
- “某工具坏了”这类可能很快过时的永久负面结论；
- 只适用于某个PR编号或当天任务的具体答案；
- 没有形成新方法的普通顺利任务。

这说明Hermes不是简单地把每次错误都追加到Skill，而是尝试区分“环境偶发事件”和“可迁移的操作经验”。最终判断仍由LLM完成，因此并非确定性正确。

### 2.4 后台Review与主任务分离

Review发生在主回答交付之后，避免用户等待复盘过程。后台fork通常：

- 继承主Agent的模型或使用单独辅助模型；
- 获得会话快照或压缩摘要；
- 使用受限的Memory/Skill管理工具；
- 与主会话持久化隔离；
- 禁止递归触发自己的Review。

这个设计把“工作”和“反思”分开：主Agent专注完成当前任务，后台副本负责提炼长期价值。

## 三、Skill不只是保存，还会持续维护

### 3.1 Agent-managed Skills

Hermes的`skill_manage`支持：

| 动作 | 用途 |
|---|---|
| `create` | 创建新的Skill |
| `patch` | 局部修复，优先方式 |
| `edit` | 大规模重写 |
| `write_file` | 添加reference、template或script |
| `remove_file` | 删除配套文件 |
| `delete` | 删除Skill |

Hermes偏好局部patch，因为它比完整重写更容易审阅、归因和回滚。

### 3.2 优先更新已有类别，而不是不断新建

后台Review的落点优先级是：

```text
1. 更新本次已经加载的Skill
2. 更新现有的同类umbrella Skill
3. 在现有Skill下添加reference/template/script
4. 没有合适归属时才创建新Skill
```

例如，不应为一次问题创建：

```text
fix-pr-3718-tls-error
```

而应更新：

```text
deployment-troubleshooting/
├── SKILL.md
└── references/corporate-tls-proxy.md
```

这体现了Hermes当前强调的“类别级Skill库”，而不是一会话一Skill。

### 3.3 `/learn`显式教学入口

除自动Review外，Hermes还提供`/learn`入口，让用户明确要求把一个目录、URL、刚完成的流程或文字说明提炼成可复用Skill。

它与后台学习的区别是：

```text
后台Review：系统根据计数和语义判断自动寻找经验
/learn：用户明确指定要学习的对象
```

后者更可控，适合团队把成熟runbook主动交给Hermes。

## 四、Curator：解决“越学越乱”

自我改进系统的难点不只是写入，还包括遗忘、合并和治理。Skill持续增长后容易出现：

- 多个Skill重复；
- 旧Skill失效；
- 类别过细；
- 描述冲突；
- 默认Skill过多导致索引和上下文噪声增加。

Hermes的Curator承担Skill库维护工作，可结合使用情况进行整理、归档、去重和合并。用户也可以pin重要Skill，避免被自动归档或合并。

闭环因此不只是：

```text
任务 → 新Skill
```

而是：

```text
任务经验
  ↓
创建或更新Skill
  ↓
使用统计
  ↓
Curator整理、合并、归档
  ↓
维持较小且可发现的Skill库
```

这一层很重要，因为没有治理的“持续学习”最终往往只是持续堆积上下文。

## 五、学习过程可观察、可控制

Hermes不仅写Memory和Skill，还提供让用户观察和治理这些产物的入口。

### 5.1 `/journey`

`/journey`以时间线方式展示Agent积累的Memory和Skill，用户可以查看、编辑或删除。它试图让“Agent知道什么”不再完全隐藏在后台文件中。

### 5.2 Skill写入审批

可以配置：

```yaml
skills:
  write_approval: true
```

此时Agent提出的create、patch、edit、delete和支持文件修改先进入pending，用户查看diff后再批准。

### 5.3 Skill安全扫描

可选配置：

```yaml
skills:
  guard_agent_created: true
```

它对明显的凭据收集、Prompt Injection或外泄指令做启发式检查。不过该扫描默认关闭，且不能替代完整安全评审或效果评测。

### 5.4 Checkpoint与回滚

Hermes可在文件修改前创建工作目录快照，允许通过rollback恢复。Skill本身也是文本文件，适合使用diff、版本控制和审批。

## 六、离线Skill进化：DSPy + GEPA

Hermes还有独立开源项目`hermes-agent-self-evolution`，尝试将Skill优化从单次LLM反思提升为评测驱动搜索：

```text
当前SKILL.md
  ↓
构造train / validation / holdout
  ↓
包装成DSPy Module
  ↓
GEPA读取失败和反馈，生成候选Skill文本
  ↓
验证集选择
  ↓
留出集比较baseline与candidate
  ↓
输出候选Skill与指标
```

这仍不是模型参数训练。被优化的是`SKILL.md`文本，底层LLM可以保持冻结。

当前证据边界：

- Phase 1 Skill文本优化原型已开源；
- 工具描述、system prompt、Python工具代码和完整持续循环仍主要处于规划；
- 当前主路径评分仍有关键词重合等原型性简化；
- README描述的完整测试、benchmark和自动PR门禁尚未全部接通。

因此，在线Review是Hermes主产品已经集成的学习机制；DSPy+GEPA是更实验性的离线优化路线，两者不能混为一谈。

## 七、另一组特色：同一个Agent跨平台长期存在

Hermes强调的不是“在某个聊天窗口里运行一次”，而是同一套状态和能力可以通过多个入口访问：

- CLI/TUI；
- Desktop；
- Telegram、Discord、Slack、WhatsApp、Signal、Matrix等；
- ACP兼容IDE；
- OpenAI兼容HTTP API；
- Cron和Webhook。

这意味着用户可以在Telegram中给云端Hermes下任务，Hermes在Docker、SSH、Daytona或Modal环境执行，再把结果送回消息平台。

这种“Agent住在基础设施中，而不是绑定用户笔记本或IDE”的部署哲学，是Hermes产品定位的显著特点。

## 八、模型和辅助任务分离路由

Hermes支持为不同工作选择不同模型：

```text
主任务         → 主模型
上下文压缩     → 辅助模型
后台Review     → 辅助模型
视觉理解       → 视觉模型
主供应商失败   → fallback模型
```

近期官方发布还强调更便宜的后台自我改进：当Review路由到另一个模型时，可以用对话摘要替代完整冷启动上下文；使用主模型时则尽量复用prompt cache。

这让“反思”不必一直占用最昂贵的主模型，也使自我改进成本可以单独控制。

## 九、Skill、Memory和SessionDB构成的三层状态

Hermes的长期能力可以总结为：

```text
Memory
  小、常驻、事实性

Skill
  大、按需、程序性

SessionDB
  完整历史、按查询召回
```

`session_search`使用SQLite FTS5查找真实历史消息，不需要每次把所有会话发送给模型。需要时才把相关片段召回当前上下文。

三层结构分别控制：

- 常驻token成本；
- 可复用流程长度；
- 历史证据覆盖范围。

这比单一“长期记忆向量库”更明确地划分了信息的用途和生命周期。

## 十、子Agent、Cron和工具的意义

这些不是Hermes独有算法，但它们与长期Agent定位组合得比较紧密：

- `delegate_task`可让多个隔离子Agent并行处理子任务；
- `cronjob`让Agent在用户不在线时执行定时工作；
- Gateway让同一Agent从多个消息平台接收任务；
- `execute_code`允许用Python编排Hermes工具，减少长工具链中的模型往返；
- MCP用于接入数据库、GitHub或内部服务；
-终端可运行在Local、Docker、SSH、Daytona、Singularity或Modal。

这些能力让自我改进不只是聊天偏好学习，而能积累真实执行环境中的程序性经验。

## 十一、Hermes自我改进的完整案例

用户要求Hermes修复企业网络中的部署失败：

```text
1. 读取部署配置
2. 运行部署，出现TLS错误
3. 检查服务端证书链
4. 初次修复失败
5. 检查代理设置
6. 发现企业代理替换证书
7. 导入组织CA
8. 重新部署
9. 运行健康检查
10. 验证回滚路径
```

任务完成后：

```text
工具迭代达到Review阈值
  ↓
主Agent先告诉用户部署成功及证据
  ↓
后台Review检查会话
  ↓
判断“企业代理TLS诊断”具有复用价值
  ↓
寻找已有deployment-troubleshooting Skill
  ↓
patch一段稳定流程
```

合理的沉淀内容是：

```markdown
当TLS校验只在企业网络内失败时：
1. 在关闭校验前先检查实际证书链；
2. 判断叶证书是否由TLS拦截代理签发；
3. 将组织CA加入工作负载信任库；
4. 重新执行部署和健康检查；
5. 不要把verify=false保存为长期解决方案。
```

不合理的沉淀内容是：

```text
“部署工具有问题，以后禁用TLS校验。”
```

若开启`write_approval`，该patch会先进入pending，由用户查看diff后批准。未来相似部署任务加载这个Skill时，Agent会从已验证的诊断路径开始。

完整状态变化为：

```text
TASK_RUNNING
  ↓
TASK_VERIFIED
  ↓
BACKGROUND_REVIEW
  ├─ 没有通用经验 → NO_CHANGE
  └─ 有通用经验 → SKILL_PATCH_PENDING
                         ├─ 用户拒绝 → REJECTED
                         └─ 用户批准 → ACTIVE_SKILL_vN+1
```

证据边界：在线Review能证明任务轨迹中出现了某种经验，但不能自动证明更新后的Skill在其他任务上更有效。后者仍需要回归评测、人工审查或离线GEPA管线。

## 十二、优势与主要风险

### 优势

- 不训练权重也能积累用户和环境经验；
- Memory、Skill和历史会话用途分离；
- 工作与后台反思分开，不阻塞主回答；
- Skill是可读文本，易审阅、版本化和回滚；
- Curator开始处理知识膨胀与重复问题；
- 同一个Agent可跨消息平台和执行环境长期运行；
- 主任务和后台学习成本可以独立路由。

### 风险

- LLM可能把偶发事件误判为通用规律；
- 用户纠正不一定适用于所有同类任务；
- 自动Skill会成为未来Prompt的一部分，错误可能反复放大；
- Skill或Memory可能携带Prompt Injection；
- Curator错误合并可能丢失重要条件；
- 没有独立eval时，“保存了经验”不等于“能力真的提高”；
- 如果Skill写入和终端权限过宽，后台Agent可能产生不期望的副作用。

更稳健的部署方式是开启Skill写入审批、使用最小工具权限、保存版本和diff，并对高价值Skill建立独立回归集。

## 十三、最终评价

Hermes最有辨识度的设计可以概括为：

```text
长期运行的通用Agent
+ Memory / Skill / SessionDB分层状态
+ 规则触发的后台LLM复盘
+ Agent自主维护Skill
+ Curator治理增长中的知识库
+ 多平台入口和可替换执行环境
+ 主模型与辅助学习任务独立路由
```

它没有解决“Agent如何保证学到的知识永远正确”，但把自我改进从一句抽象口号拆成了可观察的工程组件：触发器、后台Review、持久化文件、写入审批、Skill治理和实验性离线优化。这是Hermes最值得深入研究的部分。

## 十四、主要官方来源

- [Hermes Agent官方文档](https://hermes-agent.nousresearch.com/docs/)
- [Features Overview](https://hermes-agent.nousresearch.com/docs/user-guide/features/overview/)
- [Skills System](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/)
- [Architecture](https://hermes-agent.nousresearch.com/docs/developer-guide/architecture)
- [Tools & Toolsets](https://hermes-agent.nousresearch.com/docs/user-guide/features/tools/)
- [Security](https://hermes-agent.nousresearch.com/docs/user-guide/security/)
- [Configuration](https://hermes-agent.nousresearch.com/docs/user-guide/configuration)
- [Hermes Agent官方仓库](https://github.com/NousResearch/hermes-agent)
- [Hermes Agent Releases](https://github.com/NousResearch/hermes-agent/releases)
- [Hermes Agent Self-Evolution](https://github.com/NousResearch/hermes-agent-self-evolution)

