# Contributing to claude-lark

Thanks for your interest! / 感谢你的关注！

## Development Setup

```bash
git clone https://github.com/ysyecust/claude-lark.git
cd claude-lark
```

No dependencies needed — the project uses only Python stdlib.

无需安装依赖，项目仅使用 Python 标准库。

## Running Tests / 运行测试

```bash
python3 -m pytest tests/ -v
```

## Guidelines / 开发规范

- **Zero dependencies** — Python 3.8+ stdlib only. Do not add pip packages.
- **Silent failures** — the hook must never block Claude Code. All errors should be caught silently.
- **Keep it simple** — this is a single-file tool. Avoid over-engineering.

## Submitting Changes / 提交变更

1. Fork the repo / Fork 仓库
2. Create a feature branch / 创建特性分支
3. Add tests for new functionality / 为新功能添加测试
4. Ensure all tests pass / 确保所有测试通过
5. Submit a Pull Request / 提交 PR

## Reporting Issues / 报告问题

Open an issue on GitHub with / 在 GitHub 上提交 issue，包含：

- Python version (`python3 --version`)
- Claude Code version
- Steps to reproduce / 复现步骤
- Expected vs actual behavior / 预期与实际行为
