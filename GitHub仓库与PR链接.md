# GitHub 仓库与 PR 链接

> 本文件为交付说明，不属于项目功能代码。

## 仓库（公开）

https://github.com/water0810zou-blip/club-recruitment-data-cleaning

## 三次 PR（均已合并进 main）

| PR | 对应需求 | 该 PR 的改动文件（diff 只含本次需求） | 链接 |
| --- | --- | --- | --- |
| #1 | 需求1 读入与概览 | `src/common.py`、`src/overview.py`、`tests/test_overview.py` | https://github.com/water0810zou-blip/club-recruitment-data-cleaning/pull/1 |
| #2 | 需求2 校验与清洗 | `src/validate.py`、`tests/test_validate.py` | https://github.com/water0810zou-blip/club-recruitment-data-cleaning/pull/2 |
| #3 | 需求3 统计与导出 | `src/report.py`、`run_all.py`、`tests/test_report.py`、`docs/*`、`scripts/*` | https://github.com/water0810zou-blip/club-recruitment-data-cleaning/pull/3 |

三个 PR 按需求顺序**依次创建并合并**（feat/01 → 合并 → feat/02 → 合并 → feat/03 → 合并），
这样后一个 PR 的 diff 相对 main 恰好只包含本次需求的改动。

## 分支

- `main`：三次需求全部合并后的完整代码
- `feat/01-overview`：需求1 读入与概览
- `feat/02-validate`：需求2 校验与清洗
- `feat/03-report`：需求3 统计与导出

## 本机这份文件夹的 git 状态

- 已配置远程 `origin` 指向上面仓库
- 本地 `main` 已指向合并后的远程 main（含 3 个 merge 提交，共 7 个提交）
- 注意：本机该目录的 `.git` 写入不稳定（有云同步/清理工具干扰），
  可能出现「命令成功但状态回滚」的现象。若远程跟踪引用缺失，执行
  `git fetch origin`（必要时多试一次）即可补齐。

## 若要把这份本地仓库换成全新克隆（最省事）

```
git clone https://github.com/water0810zou-blip/club-recruitment-data-cleaning.git
```

## 备注

- 仓库按考核要求设为**公开**；仓库内只有用固定随机种子生成的**合成示例数据**，
  不含任何真实同学信息。若之后放入真实报名数据，可在 GitHub 设置里改为私有，
  并把考核方加为协作者。
