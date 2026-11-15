# OH6.6 B2N 显示对象构建审查：#12

## 已核验结果

- Run: https://github.com/GreyDust-114/OpenHarmony_on_Nokia_SD660/actions/runs/43733365831
- GitHub conclusion: success
- Workflow commit: `a63db295e99616e46b60fc1aa32c0be5f6a90ad8`
- 本地 ZIP: `research-oh66-b2n-dts-43733365831-1.zip`
- ZIP 大小: 15,046,540 bytes
- ZIP SHA256: `be72e9d35c7193f5b5a87e40519a2c0f8a7f66092b643a8f5bf8c6836dd25c4b`
- SHA256 与 GitHub artifact digest 一致。
- 69 ZIP entries，内部 SHA256SUMS 中 68 个文件全部通过。
- 解包前检查了路径、符号链接标志和解包总大小。

## 编译日志

`logs/44-compile-ft8716u-panel-object.log` 明确包含：

```text
CC drivers/gpu/drm/panel/panel-ft8716u.o
```

对象目标正常退出。OH6.6 API 转换后的 panel C 源码已通过编译。

`logs/42-compile-device-trees.log` 和 `logs/43-compile-ft8716-object.log` 分别记录 DTB 与触摸对象编译。最终内核日志 `logs/45-compile-kernel.log` 完成 Image.gz，检测到 0 条 error、17 条 warning。

## DTB

B2N DTB:

- 大小: 43,202 bytes
- SHA256: `feee5d3ec664d637108207626597f0066fd2001c2eec444ada7b3c724f261b72`

Artifact 保存的实际 DTS 中：

- mdss、mdss_dsi0、mdss_dsi0_phy、mmss_smmu 为 okay；
- DSI panel compatible 为 `focaltech,ft8716u`，地址 0；
- panel 与 mdss_dsi0_out 互相引用 endpoint；
- data-lanes 为 0/1/2/3；
- 当前草案 reset 为 GPIO62，低有效，后续仍需对照 B2N 面板与 NT50356 GPIO 职责核实；
- GPU 仍 disabled；
- 原有 FT8716 触摸二进制属性检查通过。

本轮自动二进制检查 profile 仍是 b2n-touch，尚未加入显示 endpoint/power contract。

## 对象编译与镜像接入的区别

本轮 panel 驱动仅被显式对象目标编译；补丁尚未增加该驱动的 Kconfig/Makefile 项。System.map 中没有 mdss_dsi_ft8716u 符号。

最终 Image.gz:

- 大小: 13,624,509 bytes
- SHA256: `1e10a109a3b850dd73262adfd48118d4ef624a0e5615764ee8a0ae7c96ff309e`

该 hash 与前一基线相同，符合“新增 panel 对象未链接入 Image”的实际构建状态。

有效配置：

```text
CONFIG_DRM=y
CONFIG_DRM_MSM=m
CONFIG_DRM_MSM_MDP5=y
CONFIG_DRM_MSM_DSI=y
CONFIG_DRM_PANEL_SIMPLE=m
```

MSM 为模块，但当前目标只构建 Image.gz，没有构建/打包对应显示模块；下一阶段应选择内建显示驱动或显式打包所需模块。

## 下一阶段

链接接入轮已实现专用 `DRM_PANEL_B2N_FT8716U` Kconfig/Makefile；
将 QCOM_OCMEM、QCOM_LLCC 和 BACKLIGHT_CLASS_DEVICE 设为内建，解除 MSM 的
模块依赖上限。配置验收要求 MSM/MDP5/DSI/14nm PHY/panel 为 y，最终
System.map 必须包含 panel、MSM、DSI 三个驱动的定义符号，并保存
`linked-display-validation.json`。该轮保留 #12 panel 的命令及 mode 内容，
只验证链接接入，不将参考板参数宣称为已完成的 B2N 显示适配。

1. 增加专用 panel Kconfig/Makefile，并验证实际链接产物。
2. 将 MSM 显示依赖配置和产物验收补齐。
3. 将参考板初始化序列替换为保存的 B2N 原厂序列；显式保留 packet type、payload、LP/HS 和 delay，特别是两字节 0x39 长写。
4. 用原厂 timing、reset、物理尺寸替换参考板占位参数；2160 行高度已编译，但其余 mode 参数尚待证据对齐。
5. 接入 NT50356 bias/backlight、供电、复位顺序与显示 DTB 合同。

本轮确认的里程碑是 panel API/对象编译通过和显示 DTS 生成；没有进行手机操作。
