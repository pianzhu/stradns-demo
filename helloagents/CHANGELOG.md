# Changelog

本文件记录项目所有重要变更。
格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/),
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 新增
- 初始化知识库文档结构

### 变更
- command_parser 兼容对象数组输出并更新回归用例与文档
- 调整 tests 目录结构，单元测试迁移至 tests/unit，集成测试与夹具迁移至 tests/integration
- 命令解析改为仅接受对象数组，检索管线支持多命令返回并新增 retrieve_single

### 修复
- 修复 bulk 量词场景向量检索兜底与查询文本清洗
