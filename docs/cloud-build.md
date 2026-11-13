# 用 GitHub Actions 编译研究内核

## 当前能做与不能做的事

已准备 `.github/workflows/kernel-build.yml`，只由 **workflow_dispatch 手动触发**，不随push/PR自动编译。每次选择一个目标，默认并行度2、最长120分钟；产物默认保留3天。

这能把当前的内核编译工作从本机搬到GitHub，但**不是把完整OpenHarmony流程原样放进普通runner**。尚未实际运行任何Actions任务，不能宣称云编译已经成功。

| 手动目标 | 输入 | 目标/意义 |
|---|---|---|
| `nokia44-baseline`（建议第一次选它） | Nokia社区4.4.302固定提交，SD660基础defconfig + Nokia/B2N配置片段 | 编译`Image.gz-dtb`，先证明B2N社区基线可构建；**尚无OH token/HDF/HAL适配** |
| `oh66-ft8716` | OH6.6固定提交 + 已评审7行补丁，通用arm64 defconfig | 先编FT8716驱动对象，再编`Image.gz`；**没有B2N新DTS、面板驱动或完整OH系统** |

两个输出均为研究内核，**不是可以直接刷到手机的boot.img**。它们不包含已验证的bootloader/ramdisk/分区恢复方案。编译成功也不能证明本机启动、显示或短信可用。

## 普通runner的资源限制

本次直接读取的[GitHub官方runner文档](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)列出，标准x64 Linux：

| 仓库类型 | CPU | RAM | SSD |
|---|---:|---:|---:|
| 公共仓库 | 4 | 16 GB | 14 GB |
| 私有仓库 | 2 | 8 GB | 14 GB |

文档说明公共仓库使用标准GitHub-hosted runner的计算免费。**这不等于所有runner和artifact存储都无限免费**；私有仓库、较大runner与超额用量应先检查账户[Actions计费](https://docs.github.com/en/billing/concepts/product-billing/github-actions)。本次未能成功抓取计费页，不在此固化可能变化的免费分钟数、存储额度或价格。

- 单内核构建比完整OH小得多，适合作为当前尝试；仍以实际runner的可用空间和日志为准，不能承诺一定够。
- 构建脚本在拉取内核前检查至少8GiB空闲；这只是早期门槛，不保证后续不会耗尽空间。
- 完整OH/Oniro流程此前文档预算约150–180GB，需要后续单独规划大磁盘远程构建机/runner，并核查费用。
- 现在不采用删除runner大量预装软件、拆分上传整个编译树、远程SSH“保活”等办法来掩盖空间问题。
- 不配置cache，避免一开始消耗大量缓存额度；只上传日志、配置、许可证和成功产物，不上传完整源码、out目录或vmlinux。

## 在GitHub上使用

当前指定仓库为 [`GreyDust-114/OpenHarmony_on_Nokia_SD660`](https://github.com/GreyDust-114/OpenHarmony_on_Nokia_SD660)，默认分支为`main`。本机使用隔离的`.publish-ci/`小型克隆准备最小提交，保留仓库已有历史，避免把整个研究目录加入索引。推送和触发仍须先完成GitHub身份授权；实际状态以当前会话检查为准。

本机已有Git Credential Manager时，可由用户在自己的终端运行以下命令并按提示在GitHub网页授权，**不要把token或密码粘贴到聊天中**：

```powershell
git credential-manager github login --username GreyDust-114 --device
```

该登录与手机无关，也不需要安装GitHub CLI。首次未授权时不会声称已经推送或启动构建。

1. 准备你控制的GitHub仓库。公共仓库便于使用标准runner和共享日志，但公开前务必检查文件内容；如果不想公开研究资料，可以只上传下面的最小文件集合。
2. 把以下文件保留目录结构放到仓库的**默认分支**：

   ```text
   .github/workflows/kernel-build.yml
   ci/build_kernel.py
   ci/kernel-targets.json
   ci/test_kernel_ci.py
   docs/research/drafts/ft8716-oh66-review.patch
   ```

   可同时上传本页、README与`.gitignore`。CI不需要手机采集证据、完整研究快照、短信数据或vendor二进制。

3. 在GitHub打开 **Actions → Research kernel build (no flashing) → Run workflow**。首次建议选`nokia44-baseline`、jobs=`2`，先跑一个任务，不同时展开两路大构建。
4. 若成功，再运行`oh66-ft8716`。若失败，先看最早失败阶段，不盲目换内核提交、关闭权限或添加未知工具链。
5. 在任务页下载artifact，或查看日志。无需往电脑下载源码或完整out目录；只下载需要审查的小产物。

工作流需要仓库自己的Actions启用及手动运行权限，不需要额外PAT、SSH密钥、手机root凭据或USB连接。不会把手机接到GitHub runner。

### 隐私默认保护

新增`.gitignore`默认排除：`.obsidian`、root实机证据、设备config/摘要、生成的主机状态及本机构建目录。**`.gitignore`不能撤回已经提交的文件，也不能阻止网页手动上传忽略文件。** 不要无检查地上传整个项目文件夹，尤其不要上传IMEI、短信、完整分区备份或账号密钥。

研究脚本中的离线测试有些需要本机保存的私有证据，因此云CI只运行`ci/test_kernel_ci.py`，不会尝试采集手机或上传这些证据。

## 工作流具体行为

- runner固定为`ubuntu-22.04`，不使用`self-hosted`或收费大规格标签。
- 权限仅`contents: read`；checkout不持久化token。
- checkout/upload-artifact动作固定到查询时的完整提交SHA；内核输入也固定为完整SHA。
- 只浅拉所选的一棵内核源码，不执行OH `repo sync`。
- 在runner安装Clang/LLVM/LLD14、GNU交叉工具及构建依赖；**不安装到你的电脑**。
- 旧内核使用Clang14 + GNU交叉binutils；新内核使用`LLVM=-14`。这是待首轮CI验证的工具链选择，不是已验证的Nokia原厂工具链。
- apt包的完整版本尚未完全锁定，会记录实际版本。因此当前是输入可追踪的构建尝试，不承诺跨时间逐字节可复现。
- 配置合并后检查关键Kconfig是否保留，防止条目被依赖条件静默关掉。
- OH6.6目标先检查并应用FT8716草案；没有HDF外部仓库/完整OH产品构建，不能把单内核编译说成完整OH集成。

核心脚本默认只打印计划；需要`--execute`、Linux及Actions环境才运行构建。不会删除已有source/out目录覆盖重试，不会更改启动分区。

## 产物与失败日志

artifact包括尽力保留的：

- `logs/`：资源、包安装、源码拉取、配置与编译日志。
- `kernel.config`、`System.map`（若已生成）。
- `provenance.json`：目标、源码SHA、实际阶段/状态、workflow提交、补丁hash和成功镜像hash。
- `build-plan.json`、`kernel-targets.json`、适用时的补丁及内核许可证。
- `research-kernel-not-a-boot-image/`：仅整个编译目标成功后才收集内核文件。
- `SHA256SUMS`：构建脚本结束时对当时已有文件生成的校验值。

上传步骤设为`if: always()`，但硬超时、取消或runner故障仍可能使最终清理/上传无法完成。包安装失败时，至少尝试保留安装日志，可能尚无provenance。**状态是failed时不要把残留配置或局部文件当成成功镜像。**

公开分发内核二进制需遵守其GPL等许可证，提供对应源码和修改；provenance中的链接本身不自动代替合规的对应源码交付。当前不自动创建Release。

## 首轮验证范围

本机已完成：Python CI单元测试、YAML解析和工作流bash片段语法检查（使用Git Bash的`-n`，不执行片段）。没有在本机安装编译依赖，也没有进行内核构建。

云端尚待验证：内核拉取、完整配置合并、工具链兼容性、实际空间/时间需求和编译结果。首轮失败也有价值：有固定源码/阶段日志后，才能针对真正的构建错误修复，不预先堆砌未验证补丁。
