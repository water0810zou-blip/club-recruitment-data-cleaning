# 如果 `.git` 被清空了，怎么恢复

## 为什么会需要这个文件

在 Windows 上，如果桌面开着云同步/清理类工具（微云、坚果云、网盘客户端等），
它们有时会「整理」隐藏目录，把 `.git` 里的内容清掉——表现是
`git status` 突然报 `fatal: not a git repository`，而 `.git` 目录还在、里面是空的。

仓库里附带了一份 **git bundle**（就是整个仓库的打包副本，包含全部分支与提交）：

```
docs/git-history.bundle
```

## 恢复步骤（一条条复制即可）

```bash
# 1）先看看 bundle 里有什么（不需要现有仓库）
git bundle list-heads docs/git-history.bundle

# 2）把 bundle 当成一个「远端仓库」克隆回来
git clone docs/git-history.bundle repo-restored

# 3）进入恢复出来的仓库，确认三个分支都在
cd repo-restored
git log --oneline --graph --all
git branch -a
```

`git branch -a` 应当能看到：

```
  feat/01-overview     需求1 读入与概览
  feat/02-validate     需求2 校验与清洗
  feat/03-report       需求3 统计与导出
  main                 仓库脚手架
```

## 恢复后怎么继续用

```bash
# 方式 A：就用新克隆的目录干活（推荐，最干净）
cd repo-restored
python run_all.py

# 方式 B：把代码同步回原目录（原目录里 .git 已损坏，先删掉它）
#   cd ..
#   rm -rf "招新报名数据清洗与统计/.git"
#   cp -r repo-restored/.git "招新报名数据清洗与统计/.git"
```

## 预防

- 别把工作仓库直接放在会同步的桌面/网盘目录里；放 `D:\code\` 之类的本地路径最稳。
- 有远端仓库的话，`git push` 之后即使本地 `.git` 被清也能直接 `git clone` 回来：
  `git remote add origin <地址>` 然后 `git push -u origin --all`。

## 想重新生成 bundle

```bash
git bundle create docs/git-history.bundle --all
```
