# OH6.6 B2N 显示供电构建审查（#17）

## 运行结果

- Run: https://github.com/GreyDust-114/OpenHarmony_on_Nokia_SD660/actions/runs/43833334992
- GitHub 最终状态：completed / success；job 08:41:53Z 开始，产物 09:14:42Z 写完，约 32 分钟。
- Workflow commit: `24bb303a306475ee266ee60acd7568aeeb63c806`，即 #16 的 DTS 布局修复提交。
- ZIP: `research-oh66-b2n-dts-43833334992-1.zip`，15,401,140 bytes。
- ZIP SHA256: `5f22bda9eb22481044fb3f18ecee5284fb10b7a3fb2c549a95229446a22690bf`，与 GitHub artifact digest 一致。
- 86 ZIP entries，内部 85 个文件 SHA256 全部通过；解包前检查路径、符号链接标志与展开总大小（21,573,257 bytes）。
- provenance 中 8 个补丁（3 个支持补丁 + 板级/显示/硬件/供电 4 个补丁 + 触摸评审补丁）的 SHA256 与仓库 manifest 一致；供电补丁为修复后版本 `3b38b531…599b78fbd`。

## 配置验收

`required_symbols` 全部通过（13 项），三个禁用项也按预期为未设置：

```text
CONFIG_ARCH_QCOM=y
CONFIG_I2C_QUP=y
CONFIG_PINCTRL_SDM660=y
CONFIG_INPUT_EVDEV=y
CONFIG_TOUCHSCREEN_EDT_FT5X06=y
CONFIG_DRM_MSM=y
CONFIG_DRM_MSM_MDP5=y
CONFIG_DRM_MSM_DSI=y
CONFIG_DRM_MSM_DSI_14NM_PHY=y
CONFIG_BACKLIGHT_CLASS_DEVICE=y
CONFIG_REGULATOR=y
CONFIG_REGULATOR_NT50356=y
CONFIG_DRM_PANEL_B2N_FT8716U=y
# CONFIG_KSM is not set
# CONFIG_SCSI_UFS_EXYNOS is not set
# CONFIG_DRM_MSM_DPU is not set
```

## 最终 System.map 链接验收

四个必需符号均存在，与 `linked-display-validation.json` 逐项一致：

```text
ffff8000821a0c00 d mdss_dsi_ft8716u_driver
ffff8000821a02c8 d msm_platform_driver
ffff8000821a0a38 d dsi_driver
ffff80008218e918 d nt50356_driver
```

`nt50356_driver` 进入最终内核，说明偏压驱动不只是单独对象编译。

## DTB 与显示契约

| DTB | 大小 | SHA256 |
|---|---|---|
| B2N `sdm660-nokia-b2n.dtb` | 44,090 bytes | `469d95897567224292b27ed96c85aa382a97247271a4d376648772667cbe03f6` |
| Lavender 对照 | 47,317 bytes | `e7915cf6e7c357b129653da279bec4956a0c82facea49b0bfac2b0c5381b0b6f` |

B2N 的 `b2n-touch` 与新增 `b2n-display` 两个二进制契约都通过：

- 面板节点 `/soc@0/display-subsystem@c900000/dsi@c994000/panel@0`，`reg = 0`，reset = GPIO53 低有效；
- `vddi0-supply` 解析到 `/remoteproc/glink-edge/rpm-requests/regulators-1/l11`，`regulator-min-microvolt = 1780000`（PM660 L11，1.8V）；
- 偏压节点唯一，位于 `/soc@0/i2c@c1b7000/nt50356@11`；
- bl-en/enp/enn/id 分别绑定 GPIO13/35/48/62，均为同一 GPIO 控制器。

Lavender 对照 DTB 的字节与 SHA256 与 #14 相同（47,317 bytes、`e7915cf…`），说明本轮板级改动没有影响同版本对照板。

本机用 WSL 的 `cpp`/`dtc` 对固定提交 `31c8f21` 的稀疏检出编译了同一份组合 DTS，得到与云端相同的 44,090 bytes / `469d9589…`。这也说明 #16 的失败与 #17 的修复在本地可逐字节复现和验证；完整构建仍只在一次性 runner 上执行。

## 对象编译与镜像

- `logs/57-compile-ft8716u-panel-object.log`：`CC drivers/gpu/drm/panel/panel-ft8716u.o` 成功。
- `logs/58-compile-nt50356-object.log`：`CC drivers/regulator/nt50356.o` 成功。
- `logs/59-compile-kernel.log`：0 条 `error:`、17 条 `warning:`，完成 `LD vmlinux`、`OBJCOPY Image`、`GZIP Image.gz`。
- Image.gz：13,940,859 bytes，SHA256 `d693e60b61a388709eadc4ac75fe3e27ce8d9e1dbcf4b5e580bfabe2d7da8255`；解压后 36,280,832 bytes，ARM64 Image magic 有效。

与 #14 相比：Image.gz 增加 380 bytes（13,940,479 → 13,940,859），B2N DTB 增加 888 bytes（43,202 → 44,090），Lavender DTB 不变，warning 数仍为 17 条（既有上游告警）。

## 审查方法

下载 ZIP 后按顺序检查：GitHub digest → 路径/符号链接/展开大小 → 内部 `SHA256SUMS`（85 文件）→ provenance 补丁 pin 与 `run_id`/`workflow_commit` → 必需配置与禁用配置 → 用 `ci/device_tree.py` 独立重新解析 B2N DTB 并与 artifact 契约 JSON 逐字段比对 → `System.map` 四个符号 → Image.gz 解压与 ARM64 magic → panel/bias 对象日志与 Image.gz 标记。解析结果保存为忽略目录中的 `local-analysis.json`，不进入发布仓库。

## 附：本机 DTS 复现（可选，WSL/Linux）

只编译设备树源码，不编译内核 C 代码，也不替代云构建：

```bash
# 1. 稀疏检出固定提交的 DTS/绑定目录
D=.scratch/kernel-dts; mkdir -p "$D"; git -C "$D" init -q
git -C "$D" remote add origin https://github.com/eclipse-oniro-mirrors/kernel_linux_6.6.git
printf 'arch/arm64/boot/dts/qcom/\ninclude/dt-bindings/\ninclude/uapi/\n' > "$D/.git/info/sparse-checkout"
git -C "$D" config core.sparseCheckout true
git -C "$D" fetch --depth 1 --filter=blob:none origin 31c8f21f4c95d59c8e730038b868109e9244a936
git -C "$D" checkout -q FETCH_HEAD
# 2. 在 $D 内按 kernel-targets.json 顺序对该文件 git apply 四个 DTS 补丁
# 3. 用固定树的 cpp/dtc 编 B2N 与 Lavender 对照
cd "$D" && cpp -nostdinc -I arch/arm64/boot/dts/qcom -I arch/arm64/boot/dts \
  -I include -undef -D__DTS__ -x assembler-with-cpp \
  -o /tmp/b2n.pre.dts arch/arm64/boot/dts/qcom/sdm660-nokia-b2n.dts
dtc -I dts -O dtb -o /tmp/b2n.dtb /tmp/b2n.pre.dts
```

得到的 B2N DTB 与云端 #17 逐字节一致（44,090 bytes、`469d9589…`）。提交级回归仍是 `ci/device_tree.py` 的 `check_dts_layout()` 与 `ci/test_b2n.py`，不依赖本机 dtc。

## 边界

- 这是编译级产物，不是 boot.img，不能刷机；没有在手机上运行，也没有实机亮屏证据。
- NT50356 寄存器 bias 编程默认关闭（DTS 未写 `novatek,program-bias`），只验证了 GPIO 上电时序编译进内核；实际电压码需台架验证。
- CABC/背光 DCS 亮度控制、GPU/Adreno 启用与 SMMU 实际映射、完整 OH 系统镜像仍未做。
- 配置、DTB 与链接验收只证明构建与绑定，不证明驱动在 B2N 上的运行时行为。

## 下一步

1. 台架验证 NT50356 上电时序与 bias 电压码；确认 ID 引脚实际电平（TI/Novatek 分支）。
2. 实现 CABC/背光 DCS 亮度控制。
3. 面版初始化之后的实际出图验证需要 boot 镜像与更完整的 OH 启动链，另行规划。
