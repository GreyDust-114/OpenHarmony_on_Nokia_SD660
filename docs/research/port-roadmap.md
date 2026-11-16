# B2N / OpenHarmony 移植总路线与下一步（2026-11 更新）

> 本文是当前的总路线与阶段门槛。历史轮次的详细证据和推导仍见各专项文档：
> [路线审计](route-audit.md)、[最小改动清单](minimal-port-plan.md)、[B2N DTS构建审查](oh66-b2n-dts-build-review.md)、
> [显示构建审查](oh66-b2n-display-build-review.md)、[供电构建审查](oh66-b2n-power-build-review.md)、
> [415I boot 提取](b2n-415I-boot-extraction.md)、[运行记录](oh66-cloud-run.md)。
> 前轮结论被本轮修订的地方会明确写出。

## 1. 目标与完成定义

研究目标不变：在 Nokia 7 Plus（B2N，SDM660）上完成 OpenHarmony 标准系统的**原生启动、显示、触摸**，
不追求完整手机功能或日常可用。与之前不同的是，本轮把"移植成功"拆成可独立验收、必须**真机证据**的里程碑：

| 里程碑 | 内容 | 验收证据（缺一不可） |
|---|---|---|
| K1 | 6.6 内核 + B2N DTB 在真机启动 | `fastboot boot` 临时启动；pstore 或 USB serial 取得完整 dmesg；eMMC/USB/时钟/电源正常；eMMC 未被写入 |
| K2 | 内核显示与输入工作 | DSI 面板点亮并显示内核控制台或测试图；背光与 NT50356 偏压工作；触摸 evdev 输出正确坐标 |
| U1 | OH 用户态启动 | OH init/samgr 起来，`hdc` shell 可用（可先无图形） |
| U2 | OH 桌面与触摸 | Launcher 显示在面板上，触摸可交互（先 CPU 渲染，GPU 后置） |
| U3 | GPU 加速（可选后置） | Mesa freedreno 在 OH 内可用，硬件合成分辨率/性能达标 |

"编译成功、Actions 绿标、契约 JSON 通过"都只是 K0 级证据，不能替代上表任一行。

## 2. 当前资产盘点（2026-11）

### 2.1 已经拿到的

- **OH6.6 内核显示链在云 CI 上编译/链接完成**：#17 成功产物含 `Image.gz` 13,940,859 bytes、
  B2N DTB 44,090 bytes（`b2n-touch` + `b2n-display` 契约通过）、`nt50356_driver` 等 4 个符号，
  panel/bias 对象均实际编译。详见[供电构建审查](oh66-b2n-power-build-review.md)。
- **固定内核树自带 SDM660 主线基础设施**：`sdm630.dtsi`/`sdm660.dtsi` 已含 SDHCI(eMMC)、USB3/dwc3、
  RPM/regulator 框架、MDSS/DSI/14nm PHY、Adreno A512、I2C/BLSP、TLMM 等节点，K1/K2 不需要从零写驱动。
- **真机可逆实验条件已具备**：已确认设备可用于不写分区的临时内存启动（结论级证据；设备状态、boot 镜像与分区数据仅保存在本地证据目录，不随仓库发布）。原厂 415I 设备树、面板命令、触摸与偏压参数已逐字节核对（本地证据）。
- **OH 用户态有可直接对齐的 Linux 产品**：OH 7.0-Release 的 `qemu_arm64_linux_full` 用
  `kernel/linux/linux-6.6` + 用户态 Display/Composer VDI（DRM + GBM）+ Mesa + evdev/libinput，
  不是内核 HDF display 路线，和 B2N 的 DRM/DSI/evdev 结构相容。
- **同 SoC/同架构参考**：`sdm660-mainline/linux` 的多台 SDM660 手机 DTS、FT8716U DRM panel；
  SDM845 手机（一加 6T/小米 6）已有社区 "OH + Linux 内核 + freedreno Mesa" 先例。

### 2.2 还缺的（按阻塞程度）

1. **boot.img 打包与启动参数**：目前只有 `Image.gz` 和 DTB，没有 boot v0 打包器、initramfs、cmdline 设计；
   B2N boot 是 Android header v0、page 4096、kernel 区为 `Image.gz` 后追加 DTB 集合。
2. **K1 所需内核配置/DTS 补全**：bootloader 选择 DT 需要的 `qcom,msm-id`/`qcom,board-id`、ramoops/pstore、
   USB gadget serial、fbcon、eMMC/USB/regulator/时钟的板级使能，以及调试通路设计。
3. **OH 用户态构建资源**：OH 标准系统 full 产品源码与构建需要约 **100–180GB** 磁盘和数小时构建，
   普通 GitHub Actions（4 核、约 80GB 可用盘、120 分钟上限）不够；构建宿主尚未确定。
4. **显示 VDI 对 MSM 的适配**：DRM connector/plane/atomic/fence、buffer 分配（GBM vs dumb/GEM）、
   格式/modifier 与 OH BufferHandle 的对接，均未验证。
5. **OH 用户态板级内容**：产品配置、init/fstab/权限/SELinux、MMI 设备与坐标映射。

## 3. 路线判断：以 B 为主，A 降为后备

### 3.1 推荐路线 B：OH 7.0 Linux 标准系统 + B2N 6.6 内核 + 用户态 DRM VDI

结构（与 `qemu_arm64_linux_full` 对齐，替换掉 virt 硬件部分）：

| OH 7.0 qemu full 产品 | B2N 目标 |
|---|---|
| `kernel/linux/linux-6.6` + qemu defconfig/DTS | 同一内核仓库的 `OpenHarmony-7.0-Release` 分支 + B2N DTS/板级补丁 |
| virtio-gpu → `/dev/dri/card0` | MSM DRM + DSI connector → `/dev/dri/card0` |
| virtio-input | evdev（FT8716 触摸）→ libinput → MMI |
| virtio-blk + ramdisk/system 分区 | 先 initramfs/外部存储启动，后讨论 eMMC 分区 |
| SELinux permissive、ramdisk 启动 | 同样 permissive 起步，不改动原 userdata/NV |
| 用户态 Display Composer/Buffer VDI（DRM+GBM）+ Mesa | 同一套 VDI 适配 MSM；Mesa 先 kms_swrast 后 freedreno |

依据：

1. OH 官方在 7.0-Release 就提供了完整可参考的 "Linux 内核 + DRM + Mesa + evdev" 桌面产品代码
   （`vendor_ohemu/qemu_arm64_linux_full` + `device_qemu/common/virt_full`），证明这条路是 OH 支持的方向，
   不需要照 3.0 时代"内核 HDF display/LCD HDF panel"的移植指南重写驱动模型。
2. 输入链路：MMI 通过 libinput 监听 `/dev/input`，不需要 HDF touch 驱动；evdev 是现成的。
3. 我们已有的 6.6 内核显示/触摸/偏压工作可以直接延续，不浪费。
4. 不需要 Android vendor HAL（无 libhybris、无 4.4 vendor 内核），系统内聚性和可复现性更好。

主要风险（详见 §6）：MSM DRM 与 VDI 的 buffer/fence/plane 兼容性未验证；OH full 构建资源；
内核分支从 6.1-Release 迁到 7.0-Release 需要重放补丁。

### 3.2 后备路线 A：Oniro hybris（vendor 4.4 内核 + Halium 10 + libhybris）

为什么降为后备（本轮新证据）：

- Volla 手机上已验证的 Oniro 形态是 **5.10/6.1 vendor 内核 + Halium 12/14**，没有 4.4 先例；
  OH 7.0 需要的 kernel 适配补丁（binder token/access_tokenid/hilog/hmdfs 等）只面向 5.10/6.6，
  4.4 上回移植是高风险长尾工作。
- B2N 是 Android 10，HAL 版本是 gralloc/mapper 3.0/2.x 级别；Oniro 现用 libhybris/链加载脚本面向
  mapper@4.0/composer@2.x，版本错配未验证。
- Oniro 没有公开的手机预构建镜像，仍需自建 180GB 级 OH 用户态；A 路线并不能省掉用户态构建这一关。

切换条件：若 K2 在 6.6 上经 2–3 轮真机迭代仍拿不到显示/触摸证据，或 OH 用户态在 MSM DRM VDI 上出现
不可绕过的硬阻塞，再启动 A 路线的 Halium 10 可行性 spike。**在此之前不再并行投入 A。**

## 4. 分阶段计划

### P0：boot 基础设施 + K1（1–2 周，可立即开始，前半段不需要手机）

| 工作包 | 产出 | 验收 |
|---|---|---|
| P0-1 boot 打包器 | `ci/build_boot_image.py`：boot v0 header、`Image.gz`+B2N DTB、initramfs cpio、cmdline、结构自检 | 本地/CI 单测覆盖 header 字段、页对齐、尺寸边界；产物明确标注"研究件，不可刷" |
| P0-2 内核启动补全 | B2N DTS 增加 `qcom,msm-id`/`qcom,board-id` 等 bootloader 选择属性、reserved-memory+ramoops、sdhci、dwc3+PHY、rpm/时钟、fbcon、pstore、gadget serial；新增 `oh66-b2n-boot` CI 目标 | 配置验收 + DTB 契约 + `Image.gz`；provenance 记录全部输入 |
| P0-3 真机 K1 | `fastboot boot` 研究 boot 镜像，pstore/USB serial 取日志 | 完整 dmesg、eMMC 未写入、可随时重启回 Android |
| P0-4 OH 基线锁定 | 把内核 pin 迁到 OH 7.0-Release 的 `kernel_linux_6.6`，重放 B2N 补丁，记录 commit SHA；CI 继续通过 | 补丁全部 apply、DTB 契约与 #17 等价 |
| P0-5 构建资源 spike | `qemu_arm64_linux_full` 的 repo 清单、磁盘/内存/时间实测或估算，构建宿主方案对比 | 形成明确预算与选型，不盲目下载 180GB |

### P1：K2 真机显示/触摸

- 面板 modeset（fbcon 或最小 DRM 测试程序）、背光 DCS 与 NT50356 偏压时序上机验证。
- 触摸 evdev 节点、坐标、中断验证。
- 并行：拉取 `device_qemu/common/virt_full` 的 Display VDI 源码，做 MSM 适配清单
  （connector/plane/atomic/fence/format/buffer 分配），写验证计划。

### P2：U1 OH 用户态启动

- 在选定宿主构建 OH 7.0 arm64 full 产品（或裁剪产品），先 ramdisk/外部存储启动，不改 eMMC 分区。
- 调 init/fstab/权限/SELinux（permissive）、`hdc` shell、日志通路。

### P3：U2/U3 桌面与触摸/GPU

- Display VDI(MSM) 出图 + MMI/libinput 触摸；先 `kms_swrast` CPU 渲染，再 freedreno（Adreno 512）。
- 验收：截屏/录屏 + 触摸事件日志；性能数字作为 U3。

## 5. 立刻要做的 5 件事（按顺序）

1. **P0-1 boot 打包器**（纯软件，可离线测试）——没有它后面所有真机实验都做不了。
2. **P0-2 内核启动补全 + 新 CI 目标**（P0-2 与 P0-1 可并行）。
3. **P0-5 构建资源 spike**（不需要手机，决定用户态在哪构建）。
4. **P0-4 OH 7.0 内核基线迁移**（决定用户态与内核版本对齐）。
5. **P0-3 真机 K1**（需要 §7 的授权）。

## 6. 风险清单

| 风险 | 影响 | 缓解 |
|---|---|---|
| MSM DRM 与 OH Display VDI 的 buffer/fence/format 不匹配 | U2 无法出图 | P1 先用 `modetest`/最小 composer 程序验证，再改 VDI；必要时用 CPU 合成 + dumb buffer 起步 |
| OH full 构建资源（100–180GB、数小时） | 用户态无法落地 | P0-5 先定宿主；优先评估"官方预构建镜像 + 只重编设备层"的可行性（未证实可得） |
| 内核 6.1→7.0 分支迁移补丁冲突 | 进度回退 | 每次迁移跑完整 CI 契约；保留 6.1 成功基线可回退 |
| 主线段缺失 modem/camera/充电等 | 只能做显示/触摸/桌面 | 明确研究范围，不承诺完整手机功能 |
| 真机实验中断短信/日常使用 | 影响用户 | 短时实验、失败即重启回 Android、不写分区；见 §7 |
| 编译绿标被误当运行证据 | 结论失真 | 所有里程碑必须真机日志/画面 |

## 7. 红线与所需授权

红线（与之前一致，仍然有效）：

- 不写入 eMMC 任何分区（boot/system/vendor/userdata/NV/persist）除非另行授权并完成备份/恢复演练。
- 实验系统禁止挂载原 userdata/NV 为可写；`fastboot boot` 只做内存启动。
- 不做未经授权的重启、刷写、驱动部署；手机承担短信接收/转发。
- 每个真机阶段结束后恢复到 Android 10 正常启动。

需要用户拍板的事项见随附说明：路线选择、真机实验授权与节奏、OH 构建宿主资源。

## 8. 来源（本轮新证据）

- [OH 7.0-Release manifest](https://github.com/openharmony/manifest/blob/OpenHarmony-7.0-Release/ohos/ohos.xml)：`kernel/linux/linux-6.6` 与全量组件版本。
- [qemu_arm64_linux_full 产品配置](https://github.com/openharmony/vendor_ohemu/blob/master/qemu_arm64_linux_full/config.json)：standard 系统、graphic、multimodalinput、ramdisk、SELinux permissive。
- [virt_full 内核构建](https://github.com/openharmony/device_qemu/blob/OpenHarmony-7.0-Release/common/virt_full/kernel/BUILD.gn)：`kernel/linux/linux-6.6`。
- [virt_full 显示 VDI 构建](https://github.com/openharmony/device_qemu/blob/master/common/virt_full/hardware/display/BUILD.gn)：用户态 Composer/Buffer VDI + DRM + GBM，非内核 HDF display。
- [OH Display VDI 适配指南](https://github.com/openharmony-rs/openharmony-docs/blob/a7f3e3d2f28997d18cd0ec66067dbef9a3a3362f/zh-cn/device-dev/driver/driver-peripherals-display-vdi-des.md)。
- [Oniro Volla 手机移植](https://docs.oniroproject.org/device-development/developer-boards/volla-phones/)（后备路线 A 的参考架构）。
- [FOSDEM 2026: Bringing OpenHarmony to phones — lessons from Oniro](https://archive.fosdem.org/2026/schedule/event/SYBWKY-bringing_openharmony_to_phones_lessons_from_the_oniro_porting_effort/)。
- [SDM845 社区 OH + Linux 6.1 + freedreno 报道](https://www.ithome.com/0/677/690.htm)（社区先例，未在本项目验证）。
- 本地证据：[415I boot 提取](b2n-415I-boot-extraction.md)、[#17 供电构建审查](oh66-b2n-power-build-review.md)。
