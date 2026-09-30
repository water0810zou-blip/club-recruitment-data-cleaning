# 推送到 GitHub 并开出 3 个 PR

本地仓库已经准备好：`main` 上是脚手架，三个需求分别在三个**依次堆叠**的分支上。

```
main              chore: 初始化仓库骨架与示例数据
 └── feat/01-overview   feat(需求1): 读入 CSV 并打印概览
      └── feat/02-validate  feat(需求2): 校验规则与问题清单导出
           └── feat/03-report   feat(需求3): 统计与导出
```

> 为什么是「堆叠」而不是三条都从 main 拉出来？
> 因为三个需求是逐步加功能的，后者依赖前者的代码。堆叠分支 + **按顺序合并**
> 能让每个 PR 的 diff 只显示本次需求改了什么，评审起来最清爽。

## 一、在 GitHub 上建一个空仓库

网页上 New repository，**不要**勾选 “Add a README / .gitignore / license”（否则推送会冲突）。
假设仓库地址是 `https://github.com/<你的用户名>/smbu-signup-tool.git`。

## 二、关联远端并推送全部分支

在项目目录下执行：

```bash
git remote add origin https://github.com/<你的用户名>/smbu-signup-tool.git
git push -u origin main
git push -u origin feat/01-overview feat/02-validate feat/03-report
```

如果之前已经加过 origin，用 `git remote set-url origin <新地址>` 改。

怎么证明真的推上去了：

```bash
git ls-remote --heads origin      # 应能看到 main 与三条 feat/* 分支
```

## 三、依次开 3 个 PR（**开一个合并一个**）

每个 PR 的 base 都选 `main`，说明内容直接从 `docs/` 里复制。

### PR #1

- base: `main` ← compare: `feat/01-overview`
- 标题：`feat(需求1): 读入 CSV 并打印概览`
- 描述：复制 `docs/PR-01-读入与概览.md`
- 合并后再进行下一步

### PR #2

- base: `main` ← compare: `feat/02-validate`
- 标题：`feat(需求2): 校验规则与问题清单导出`
- 描述：复制 `docs/PR-02-校验与清洗.md`

### PR #3

- base: `main` ← compare: `feat/03-report`
- 标题：`feat(需求3): 统计与导出`
- 描述：复制 `docs/PR-03-统计与导出.md`

> 若第 2 个 PR 的 diff 里出现了需求1 的文件，说明第 1 个 PR 还没合并到 main，
> 先合并 PR #1 再刷新即可；也可以临时把 base 改成 `feat/01-overview`。

## 四、用 GitHub CLI 的话（可选）

```bash
# 按顺序执行，不要一次开三个
gh pr create --base main --head feat/01-overview \
  --title "feat(需求1): 读入 CSV 并打印概览" --body-file docs/PR-01-读入与概览.md
# 合并 PR #1 之后：
gh pr create --base main --head feat/02-validate \
  --title "feat(需求2): 校验规则与问题清单导出" --body-file docs/PR-02-校验与清洗.md
# 合并 PR #2 之后：
gh pr create --base main --head feat/03-report \
  --title "feat(需求3): 统计与导出" --body-file docs/PR-03-统计与导出.md
```

## 五、提交者身份

提交目前用的是本机的 git 配置（`git config user.name` / `user.email`）。
如果这不是你想在 GitHub 上显示的身份，可以先改：

```bash
git config user.name  "你的 GitHub 昵称"
git config user.email "你的GitHub邮箱"
# 需要改写已有提交的作者信息时（尚未推送时最简单）：
git rebase -i --root    # 或者重新提交
```

## 六、推送前自检

```bash
python -m unittest discover -s tests     # 必须是 OK
python run_all.py                        # 一把跑通
git status --short                       # 应当是干净的
```
