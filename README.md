# 华理 · 校园脉动 —— 校园舆情与思想动态育人平台

基于 BettaFish（微舆）定制的华东理工大学校园舆情与学生心理健康感知平台，线上地址 https://smydashuaige.2026515.xyz （需登录）。

本仓库最初是 2026-10-12 从线上 `bettafish` 容器 `/app` 取回的代码快照。2026-10-20 的教师反馈版本基于合并 PR #7 后的 `ed7ecf8`，分支为 `feat/teacher-feedback-20261020`。

## 2026-10-20 校园体验与研究质量修订

本轮修订继续纳入 PR #8，完整说明见 [校园体验修订说明](校园体验修订说明_20261020.md)。扩充校园分类词汇与意图识别，次日参考改为整数篇；青年热点每平台十条，按本站升温指标排序；梗文化采用十种表达的释义库，分别标注参考资料、采集用例和搜索入口。每日用量改为日期卡片，恢复队友的小腊肠狗动画并增加校园便签与图标。

育人工坊先按原始主体检索，再生成基于材料的提纲；过滤跑题来源，区分来源类型和事件日期。报告仍为四章，A4 正文按内容自然分页，页数随正文长度变化。报告模型使用实测的免费 Minimax 路线，原免费模型保留备用；正式使用需人工审阅事实和引用。

- 新增界面资源：`production/static/css/campus-play.css`、`production/static/js/campus-play.js`。
- 主题约束：`production/utils/topic_guard.py`；梗释义与来源匹配：`production/CampusPulse/meme_catalog.py`。
- 本轮发布目录：`/home/ubuntu/bettafish/deploy/campus-polish-20261020`；验证记录见 `validation/campus-v3-*.json`。
- 本轮回退：`sh /home/ubuntu/bettafish/deploy/campus-polish-20261020/rollback.sh`，恢复上一版应用及本轮模型字段，数据库保持运行。

## 2026-10-20 教师反馈版本

六个模块改用统一十二类议题和新的读取接口。首页、趋势、热点、梗文化及账本取消活动设计入口；育人工坊恢复 Query / Media / Insight → ReportEngine 的原研究流程，生成事实、传播、心理社会机制、影响观察四章报告，支持 A4 导出（本轮已改为自然分页）。

- [35 项修改与统计口径](教师反馈修改说明_20261020.md)
- 新前端：`production/static/css/campus-review.css`、`production/static/js/campus-review.js`；两个入口模板仍须保持字节一致。
- 数据读取：`production/CampusPulse/revision.py`；分类与词典：`taxonomy.py`；原研究适配与导出：`research.py`。
- 发布目录：`/home/ubuntu/bettafish/deploy/teacher-feedback-20261020`；验证、候选镜像与发布结果见 `validation/teacher-*.json`。
- 完整回退先运行 `teacher-entrypoint-20261020/rollback.sh`，再运行 `teacher-feedback-20261020/rollback.sh`，两者均位于 `/home/ubuntu/bettafish/deploy/`。回退恢复旧文件与基线镜像，不重启数据库。
- 新镜像需要 Noto CJK 字体和 Playwright Chromium。旧活动生成入口返回 410，旧版自动摘要调度停止启动；历史资料和读取接口保留。

发布验证脚本 `validation/teacher_release.py` 针对本次基线做逐文件校验；发布成功后不能再对同名发布重复执行准备步骤。后续修改应新建发布名并指定新的基线。验证服务仅监听回环地址，带测试登录的验证入口不属于生产应用。

下面记录 2026-10-19 的上一版，供历史回退和排查参考；其中活动入口已被教师反馈版替换，小腊肠装饰在本轮修订中恢复。

## 历史版本：2026-10-19

| 项目 | 内容 |
| :--- | :--- |
| 发布名 | `frontend-pulse-20261019` |
| 运行镜像 | `bettafish:candidate-frontend-pulse-20261019`（已打标为 `bettafish:local`） |
| 回退基线镜像 | `bettafish:base-frontend-pulse-20261019`（即上一版 `network-memes-20261018`） |
| 发布目录 | `/home/ubuntu/bettafish/deploy/frontend-pulse-20261019` |
| 数据库 | `bettafish-db` 未重启、未改动；容器挂载未变化 |

本次上线的文件及容器内核对过的 SHA-256：

| 路径 | SHA-256 |
| :--- | :--- |
| `production/templates/index.html` | `26dccb0983f8a9a7e8a51967768a0ba35b38f5553917f33c55b3b8bb857df7ba` |
| `production/CampusPulse/templates/pulse.html` | `26dccb0983f8a9a7e8a51967768a0ba35b38f5553917f33c55b3b8bb857df7ba` |
| `production/static/img/pulse-dachshund.webp` | `8ec7a95c0978bd06416d236c39979f14aac2e15571bccc871ffcb8cfad023250` |
| `host-deployment/Dockerfile.local` | `1806b2b288f9f6637094c375fef41b6c91d427518ad35dc7f579a10518fa1a08` |

`index.html`（`/` 页面）与 `pulse.html`（`/pulse/` 页面）必须保持完全一致。

## 历史改动：前端「脉动」版式

新版式是叠加在原有样式之上的一层（模板末尾的 `#pulse-theme-style` 与 `#pulse-theme-script`），不改动任何元素 id 和原有业务 JS。顶栏「经典」按钮可随时切回原版式，选择保存在浏览器本地。

- **视觉**：纸色底 + 墨黑主按钮 + 单一暖橙强调色，去掉渐变与发光；按钮按下有回弹手感；原图表中写死的墨绿色在运行时换成新色板，切回经典时还原。
- **华理心声**：顶部新增三张卡片 —— 心情天气（按近 7 天帖子消极表达占比换算，仅作氛围参考）、话题贴纸（大小对应帖子数，点击读原帖）、心育关怀线索（点击核验原帖）；顶栏有随近 24 小时新帖数跳动的脉搏线。
- **校内趋势**：最上方新增「趋势速览」—— 原有数字条、近十日每日发帖量堆叠柱状图、议题构成占比、各议题十日走势小图，以及「十日校园热点词云」（脉动版式下词云只在此处显示，切回经典时回到数据账本）。
- **育人工坊**：输入框上方的「华理小腊肠」随问题字数逐帧拉长、变换表情（素材为 `static/img/pulse-dachshund.webp`，6×10 共 60 帧的雪碧图），提示语随字数分档变化。
- **其他**：`⌘K / Ctrl+K` 指令面板（跳转模块、立即采集、把输入直接交给育人工坊）；手机端改为底部图标导航；尊重系统「减少动态效果」设置。

> 小腊肠的动画帧取自团队提供的参考视频。公开展示前请确认已获得原作者授权；如需替换，只要换同规格的雪碧图即可，代码无需改动。

## 发布与回退

线上发布沿用「base 镜像 + candidate 镜像」方式：先把当前运行镜像打标为 `base-<发布名>`，再以它为底叠加改动文件构建 `candidate-<发布名>`，备份主机原文件后切换。发布目录内保留 `Dockerfile`、`files/`、`backup/`、`activate.sh`、`rollback.sh`、`release-manifest.json`、`deployment-result.json` 和执行日志。

```bash
# 回退本次前端发布（恢复到 network-memes-20261018）
sh /home/ubuntu/bettafish/deploy/frontend-pulse-20261019/rollback.sh
```

注意事项：

1. `Dockerfile.local` 按文件逐个 `COPY`，新增静态资源时必须同步加一行，否则重建镜像后会 404。
2. 生产模式下模板缓存在进程内存中，修改模板后需重建镜像或重启 `bettafish` 容器才会生效。
3. 激活与回退脚本内置 `iptables -N DOCKER` 等补链保护，防止同机脚本清空 iptables 后容器无法重建。
4. 本地到服务器的 SSH 连接偶有中断，长耗时步骤建议在服务器上用 `nohup` 后台执行并查看日志，避免操作被打断在半途。

## 目录

- `production/`：运行容器里的源代码、模板、静态资源、依赖清单及上游 LICENSE。
- `host-deployment/`：服务器实际使用的 Dockerfile.local、Compose 和忽略规则。容器自带的 Compose 不是当前部署文件。
- `SOURCE_MANIFEST.json`：2026-10-12 快照时源文件的 SHA-256、大小与路径。
- `VERIFICATION.json`：快照取回后与运行容器逐文件重新核对的结果。
- `BACKUP_METADATA.json`：快照时的容器镜像 ID、启动时间、挂载关系及主机文件差异。旧备用文件只保留在本地原始快照，不上传。

## 已确认的部署方式

服务器 `/home/ubuntu/bettafish` 没有 `.git`。应用是基于上游镜像叠加定制文件构建的 `bettafish:local`，运行代码在镜像内；配置与运行数据通过目录挂载进入容器。主机项目不是完整源码副本。

## 备份边界

不包含 `.env`、`.env.web-auth`、SSH 私钥、登录凭据、数据库、业务数据、运行日志、生成报告、训练数据集、模型权重和缓存。本仓库是代码备份，不是整机或业务数据备份；原 Git 历史、队友本地未发布代码也无法从这个非 Git 部署目录恢复。GitHub 原有历史没有清理或改写。

## 恢复参考

先将 `production/` 复制到一个新的构建目录，再用 `host-deployment/` 中的部署文件覆盖该目录对应文件。安全地另行准备真实配置、数据卷和所需模型资源，在隔离环境验证后再考虑上线。当前 Dockerfile.local 引用上游 `latest`，所以重新构建不保证与现有镜像完全一致；日常发布请沿用上面的 base/candidate 叠加方式。不要直接在当前生产目录覆盖文件，也不要用空数据库替换线上数据库。

原有 `.github` 文件位于 `production/` 内，保持归档位置，不自动启用旧发布工作流。
