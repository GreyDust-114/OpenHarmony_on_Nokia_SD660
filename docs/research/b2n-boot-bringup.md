# B2N 研究启动镜像与 K1 bring-up 准备

本文记录 P0-1/P0-2 的产物：一个**仅供 `fastboot boot` 内存启动**的研究 boot 镜像，以及真机 K1
（内核启动到 initramfs）的步骤、预期与验收。它不是刷机包，也不改变手机上的任何分区。

## 已交付（#18 云构建成功）

- Run: https://github.com/GreyDust-114/OpenHarmony_on_Nokia_SD660/actions/runs/43852272454
- 提交：`cd6fa7b9d66c47f17a412783b1b0cfd7f3fe72dd`；目标 `oh66-b2n-boot`，jobs=2，约 22 分钟。
- ZIP：`research-oh66-b2n-boot-43852272454-1.zip`，30,601,831 bytes，
  SHA256 `853120d7f581bedc32ef7ea46034608fc07b63cc70189d3ba189da062ae87499`，与 GitHub artifact digest 一致。
- 107 ZIP entries，内部 106 个文件 SHA256 通过；展开 37,010,285 bytes。

### 启动镜像（artifact 内 `research-boot-not-for-flashing/`）

| 项目 | 值 |
|---|---|
| 文件 | `boot-b2n-research.img`（同目录 `DO-NOT-FLASH.txt`） |
| 大小 / SHA256 | 15,200,256 bytes / `e3d228bac950c8c211cc704358850bb6967984e0d93e342c9d3ec19f353487b5` |
| 格式 | Android boot header v0，magic `ANDROID!`，page size 4096 |
| kernel 区 | 14,108,144 bytes = `Image.gz`（14,063,714）+ B2N DTB（44,430） |
| ramdisk | 1,083,663 bytes gzip newc initramfs：`/init`、`/bin/busybox`（2,193,272 bytes 静态 busybox） |
| header 地址 | kernel 0x8000、ramdisk 0x1000000、second 0xF00000、tags 0x100（与真机 415I boot 一致） |
| cmdline | `console=tty0 console=ttyGS0,115200 console=ttyMSM0,115200n8 ignore_loglevel loglevel=8 panic=10` |
| 上限检查 | 15.2MiB ≪ boot 分区 64MiB |

### 内核侧

- 配置验收 33 项通过，覆盖显示/供电原有符号与新增启动符号（RPM/GLINK、SDM660 GCC/MMCC/GPUCC、
  interconnect、pstore/ramoops、USB gadget/dwc3/qusb2、fbcon/VT、DRM fbdev emulation）。
- System.map 四个驱动符号仍在：`mdss_dsi_ft8716u_driver`、`msm_platform_driver`、`dsi_driver`、
  `nt50356_driver`。
- B2N DTB 44,430 bytes / `3df2e50ff5e3b89ed22bdd26bea58f75847763792ac5b8dd001718b6c0190f7a`，
  `b2n-touch`+`b2n-display` 契约通过；该 SHA256 与本机用固定树 `cpp`+`dtc` 复现的 DTB 完全一致。
- `Image.gz` 14,063,714 bytes / `299b242840b15c7a417e0359cb2c675e53596b576503a7bf1a7fd96cfc659f3f`，
  解压 36,553,216 bytes，ARM64 magic 有效；编译日志 0 error、17 warning。
- `package-boot-image` 步骤日志记录了打包器输出的启动镜像 SHA256，`boot-image-report.json` 与
  `provenance.json` 的 `boot_image` 字段一致。

## 组成

- `ci/boot_image.py`：boot v0 打包器与 gzip newc initramfs 生成器；header 字段、页对齐、
  cmdline 长度、分区上限、kernel 区必须为 `Image.gz`+DTB 都有断言；`--report` 输出审计 JSON。
- `ci/fixtures/b2n-bringup-init.sh`：K1 init。只挂载 proc/sys/dev/configfs；配置 USB ACM 串口；
  把 dmesg 输出到串口和 `/dev/tty0`（面板控制台）；写 pstore；默认 300 秒后 `reboot -f`
  回到原 Android。**不挂载、不写入任何 eMMC 分区，不含 flash/dd/mkfs 类命令。**
- `ci/build_kernel.py`：目标声明 `boot_image` 时在 `compile-kernel` 之后增加
  `package-boot-image` 计划步骤，执行后校验报告哈希并把 `DO-NOT-FLASH.txt` 写入产物目录。
- `ci/kernel-targets.json`：新增 `oh66-b2n-boot` 目标（在 `oh66-b2n-dts` 基础上增加启动配置与
  `boot_image` 定义）；`oh66-b2n-dts` 目标保持不变。
- 工作流：目标选项增加 `oh66-b2n-boot`，runner 额外安装 `busybox-static`。

## 板级 DTS 增量

在原有 B2N 板级草案上只增加 K1 需要的内容（显示/触摸/供电语义未改）：

- 根节点 `qcom,msm-id = <317 0>`、`qcom,board-id = <8 0>`、`qcom,pmic-id` 与 `fih,hw-id = <7 4 2>`，
  取自原厂 415I DTB，供 bootloader 选择本 DTB；
- 复用原厂保留内存 `pstore_region@ACB00000`（2MiB）作为 `ramoops`（一次重启内的日志保留，best effort）；
- 使能 USB3 DWC3 + QUSB2 PHY 并把 `dr_mode` 设为 `peripheral`；
- memory 节点保持与主线 `sdm630.dtsi` 相同的 bootloader 回填占位。

## K1 上机步骤（待执行；需用户在场并授权）

前置：手机正常启动、能收到短信；`fastboot`/`adb` 可用（本机 PATH 已包含 platform-tools）；
手机电量充足；记录当前 slot 与 Android 版本。

1. `adb devices` 确认手机正常；如需进 bootloader：`adb reboot bootloader`（进入 fastboot 会中断 Android）。
2. `fastboot devices` 确认设备；本次只使用 `fastboot boot`，**不执行任何 `flash`/`flashall`/`erase`**。
3. `fastboot boot boot-b2n-research.img`（镜像从 #18 artifact 取出；只加载到内存）。
4. 观察两个日志通道：
   - 面板：应出现内核 fbcon 控制台/日志（照片记录）；
   - 主机：USB ACM 串口（Linux `/dev/ttyACM*`，115200 8N1）读取 dmesg 与 `b2n: initramfs reached`
     标记。
5. 300 秒后镜像会 `reboot -f` 回到原 Android；若没有自动返回，长按电源键 10 秒重启。
6. 回到 Android 后确认：正常启动、短信可用；本次没有任何写分区操作。

## 预期失败模式与处置

| 现象 | 可能原因 | 处置 |
|---|---|---|
| `fastboot boot` 报 remote error | bootloader 拒绝镜像/DTB 选择失败/解锁状态变化 | 停止实验回 Android；检查 header、`qcom,msm-id`/`board-id` 与解锁状态 |
| 屏幕亮但停在启动早期 | 内核早期驱动/时钟/regulator 问题 | 用串口或第二次实验的 pstore 取 dmesg，逐项修 DTS/config |
| 屏幕全黑、无串口 | 内核在 initramfs 前 hang（USB/显示未起来） | 长按电源回 Android；下一轮加 pstore 依赖或调整 cmdline |
| 串口无设备但面板有输出 | USB gadget/PHY 角色或主机驱动问题 | 以面板照片为主；检查 `dmesg` 中 dwc3/qusb2 探测 |
| Android 不能启动 | 极少数情况下临时镜像异常 | 强制重启回 Android；不刷写任何分区，必要时用既有 TWRP 临时启动恢复入口 |

## K1 验收标准

- 串口或 pstore 中能看到内核 dmesg 到达 `Run /init as init process`，且 USB gadget 或 fbcon 至少
  一个通道可用；
- 没有挂载/写入 eMMC 分区，实验后 Android 正常启动、短信可用；
- 记录完整 dmesg 与面板照片作为证据，写入 `docs/research/` 对应运行记录。

## 下一步

- K1 通过后进入 K2：面板显示（fbcon/最小 DRM 测试图）与触摸 evdev；失败项按 dmesg 迭代。
- 并行推进 P0-4（内核 pin 迁到 OH 7.0-Release 的 `kernel_linux_6.6`）与 P0-5（WSL+外置盘容量方案）。
- 真机实验仍遵守[移植总路线](port-roadmap.md) §7 红线与 §8 授权边界。
