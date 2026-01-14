# 任务列表：改进指令解析输出协议（多命令 + 槽位升华）

## 1. Prompt 与协议落地

- [x] 1.1 固化 system prompt：以常量/配置形式提供“严格 JSON array<object> + a/s/n/t/q/c 字段”的最终版 prompt
- [x] 1.2 为 prompt 增加最小回归用例（输入 → 期望输出形态），覆盖：单命令、多动作拆分、多目标拆分、except、any+N、@last、UNKNOWN

## 2. 消费侧解析与校验（严格但可降级）

- [x] 2.1 实现严格 JSON 解析：支持 `array<object>` 与 `array<string>`；解析失败直接降级为 UNKNOWN
- [x] 2.2 实现对象预处理：字段 `a/s/n/t/q/c` 归一化并可桥接为字符串
- [x] 2.3 实现 s 解析：支持 `*`、`,` 多房间、`!` 排除；仅排除项时隐式 include=`*`
- [x] 2.4 实现 n/t/q/c 槽位归一化：t/q 闭集，c 为整数
- [x] 2.5 实现错误处理：丢弃无效命令；若全部无效则降级为 `[{"a":"UNKNOWN","s":"*","n":"*","t":"Unknown","q":"one"}]`
- [x] 2.6 增加可观测性：记录原始 LLM 输出、解析失败原因、降级次数与 UNKNOWN 比例（注意避免日志注入）

## 3. 验证与回归

- [x] 3.1 单元测试覆盖 `openspec/changes/improve-command-parser/specs/command-parser/spec.md` 中的关键场景
- [x] 3.2 （可选）在线集成测试：真实 LLM 调用端到端验证输出契约；网络/密钥缺失时必须跳过而非失败
- [x] 3.3 灰度开关（如存在旧路径）：允许短期兼容“旧单条字符串输出”，并提供“只取第 1 条命令”的降级策略
