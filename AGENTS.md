# Project Working Rules

## HACS Release Workflow

HACS 更新不能只推送默认分支。每次对用户发布新版本时，必须完成以下全部步骤：

1. 按语义化版本规则更新 `custom_components/panasonic_smart_china_r/manifest.json` 的 `version`。
2. 在 `CHANGELOG.md` 顶部增加同版本的更新内容，只记录已验证的变更和已知限制。
3. 同步 `README.md` 顶部的版本徽章（`img.shields.io/badge/version-<version>-blue`），它不会自动跟随 manifest。2.1.5 到 2.1.6 两次发布都漏了这一步，徽章停留在 2.1.4。
4. 将最终代码合入并推送到默认分支。
5. 在最终默认分支提交上创建与 manifest 版本一致的 Git tag，格式为 `v<version>`，例如 `v2.1.1`。
6. 创建非 draft、非 prerelease 的 GitHub Release，Release notes 应与该版本 Changelog 一致，并补充必要的升级步骤或已知风险。
7. 发布后核对 Release tag、目标提交、Release 状态和远端 manifest 版本。

不得把“已修改 manifest 版本”或“已新增 `CHANGELOG.md`”单独视为 HACS 发布完成。没有 GitHub Release 时，HACS 可能将默认分支的提交哈希显示为远程版本，且不会把仓库中的 Changelog 自动显示为 Release notes。

只有当 GitHub Release 已存在并通过远程核验后，才能向用户宣布 HACS 版本已发布。
