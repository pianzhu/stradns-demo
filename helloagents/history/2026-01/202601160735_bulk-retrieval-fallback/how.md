# 技术设计: bulk-retrieval-fallback

## 技术方案

### 核心技术
- Python 3
- context_retrieval 检索管线

### 实现要点
- 增加 bulk 可用性判定：缺少向量检索器或 spec_index 时直接走常规检索。
- 向量检索查询文本改为基于原始问题的清洗版本，仅在 bulk 量词场景生效。
- bulk 场景下仅在 name_hint 明确匹配设备名称时追加到查询文本。

## 安全与性能
- **安全:** 不引入新的外部调用，不处理敏感信息。
- **性能:** 清洗逻辑为 O(n) 字符替换，影响可忽略。

## 测试与部署
- **测试:** pytest -q tests/unit/test_bulk_mode.py tests/unit/test_pipeline.py
- **部署:** 无
