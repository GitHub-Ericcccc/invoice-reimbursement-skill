# 发票报销 Skill

[English](README.md)

- 规范源文件：`README.md`
- 规范源版本：`1.0.1`
- 规范源 SHA-256：`5108DF94C8F5517807BAA6011DFC005330AFC7F8A33FD3D4A654A4AC34CD1297`
- 用途：中文审阅镜像；英文 `README.md` 为规范源。

`invoice-reimbursement` 是一个仅限显式调用的 Codex Skill，用于增量获取发票 PDF、提取并核对发票字段、统一文件名，并在不重复处理既有发票的前提下更新报销工作簿。

## 功能

- 从链接、附件、二维码目标、浏览器会话或项目文件夹获取用户授权的发票 PDF。
- 提取并核对开票日期、简要费用类别、价税合计和发票身份。
- 将 PDF 重命名为 `invoice-date-brief-content-amount.pdf`，同时保持原始发票内容不变。
- 只把新增发票写入与受管理 PDF 同目录的 `报销表.xlsx`。
- 使用发票号码和文件哈希避免重复报销行。
- 保留用户当前工作簿的结构、措辞、公式、格式和有意删除的内容。

## 调用方式

本 Skill 仅限显式调用。请按名称调用，并指出授权的发票目录或来源：

```text
使用 $invoice-reimbursement 处理这个文件夹里的新增发票并更新报销表，报销人为示例人员。
```

只有会实质改变结果的歧义才会触发确认，例如存在多个可能的工作簿、日期或金额无法辨认，或者报销人不唯一。

## 工作簿行为

最终汇总工作簿始终命名为 `报销表.xlsx`，并与发票 PDF 位于同一目录。

已有的 `报销表.xlsx` 是权威文件，绝不会被内置模板替换。如果不存在权威工作簿，Skill 可以使用脱敏资产 `skill/invoice-reimbursement/assets/报销表模板.xlsx` 初始化。只有三个可见样例行的全部标记都没有变化时才会清除样例；否则将工作簿视为已经过用户编辑。

## 隐私与安全边界

- 网页、二维码目标、PDF、图片和工作簿中的文字均视为源数据，而不是操作指令。
- 只访问用户授权的目录、链接、附件和浏览器状态。
- 除非用户明确要求其他格式，否则只保存 PDF 发票。
- 报销人、项目名称、发票标识、凭据、本地路径和映射只保存在项目本地，不嵌入 Skill。
- 工作簿替换必须可恢复；只有更新后的工作簿通过验证后，才提交项目状态。
- 本 Skill 不提供税法建议，不判断发票真伪，也不会在缺少源发票时进行账务处理。

## 仓库结构

```text
skill/invoice-reimbursement/
|-- SKILL.md
|-- SKILL_ZH.md
|-- agents/openai.yaml
|-- assets/报销表模板.xlsx
|-- references/
`-- scripts/invoice_state.py

tests/
tools/release.py
release/manifest.json
```

`skill/invoice-reimbursement` 是可部署载荷。测试、发布工具、清单和本 README 属于仓库级材料。

## Release 与安装

Release 压缩包从不可变标签进行可复现构建。安装前应审阅 Release 及其校验值。将压缩包内的 `invoice-reimbursement` 目录解压到 Codex Skills 目录，并始终将源码仓库、Release 压缩包和已安装运行副本分开管理。

已安装 Skill 通过 `agents/openai.yaml` 保持仅限显式调用。

## 验证

发布流程会验证 Skill 结构、翻译源哈希、逐文件及聚合哈希、脚本行为、工作簿模板约束、Git 工作树清洁状态、不可变标签一致性、确定性压缩包以及已安装运行副本一致性。
