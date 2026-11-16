# Nokia 7 Plus / SD660 OpenHarmony 研究索引

## 当前状态与主线

目标：原生启动、显示、触摸；暂不追求完整手机功能。

约束：手机保存个人数据并承担短信接收/转发；禁止未经授权的刷写；真机实验只走"不写分区、失败即重启回 Android"的临时启动流程。

- **当前路线**：OH 7.0 Linux 标准系统 + B2N 6.6 内核 + 用户态 DRM VDI + evdev/Mesa（路线 B），
  Oniro hybris 为后备。目标拆成 K1/K2/U1/U2/U3 真机里程碑，详见[移植总路线](port-roadmap.md)。
- **最新验证结果**：[#18](https://github.com/GreyDust-114/OpenHarmony_on_Nokia_SD660/actions/runs/43852272454) 成功产出 K1 研究启动镜像（boot v0 + 最小 initramfs，header 与真机 415I boot 一致，只供 `fastboot boot`）；内核/DTB 契约与 4 个驱动符号继续通过。真机里程碑 K1 尚未开始。前置产物审查见[供电构建审查](oh66-b2n-power-build-review.md)，启动镜像与上机步骤见[启动镜像与 K1 准备](b2n-boot-bringup.md)。
- **建议阅读顺序**：[移植总路线](port-roadmap.md) → [云构建运行记录](oh66-cloud-run.md) → 最近一次 [构建审查](oh66-b2n-power-build-review.md) → [415I 硬件事实](b2n-415I-boot-extraction.md) → 参考材料。

## 路线与计划

| 文档 | 状态 | 说明 |
|---|---|---|
| [port-roadmap.md](port-roadmap.md) | **当前权威** | 总路线、K1–U3 里程碑、阶段工作包、风险、红线与已确认决策（2026-11-16） |
| [minimal-port-plan.md](minimal-port-plan.md) | 历史计划 | 第四轮双路线最小改动清单与决策门槛；工作项已部分完成，路线优先级已被总路线修订 |

## 构建与验证记录

| 文档 | 说明 |
|---|---|
| [oh66-cloud-run.md](oh66-cloud-run.md) | 历次云构建运行记录（#1–#17）：失败点、修复提交、任务链接 |
| [oh66-b2n-dts-build-review.md](oh66-b2n-dts-build-review.md) | B2N DTS/DTB 二进制契约阶段审查 |
| [oh66-b2n-display-build-review.md](oh66-b2n-display-build-review.md) | #14：MSM/MDP5/DSI/panel 内建链接审查 |
| [oh66-b2n-power-build-review.md](oh66-b2n-power-build-review.md) | #16 布局失败与 #17 成功：供电/偏压、DTB 契约、链接与镜像审查 |
| [b2n-boot-bringup.md](b2n-boot-bringup.md) | K1 研究启动镜像（#18）：boot v0 打包、initramfs、日志通道、上机步骤/失败处置/验收 |
| [oh66-display-power.md](oh66-display-power.md) | 显示供电补丁说明：PM660 L11、NT50356 时序、构建验收 |

## 硬件与板级

| 文档 | 说明 |
|---|---|
| [b2n-415I-boot-extraction.md](b2n-415I-boot-extraction.md) | 原厂 boot 镜像提取（临时启动、未写分区）与真机硬件事实：面板命令、触摸、偏压、DT 参数 |
| [b2n-panel-hardware-adaptation.md](b2n-panel-hardware-adaptation.md) | FT8716U 原厂 120/2 命令流、timing、GPIO53 reset 与传输实现 |
| [sdm660-open-source-references.md](sdm660-open-source-references.md) | SDM660 主线 DTS/DRM/PMIC 参考与下一步适配表 |

## 归档（历史，不再维护）

第一至四轮路线审计、旧 4.4 基线审查、generic OH6.6 阶段审查、root/提权调查等已移入
[archive/](archive/README.md)（仅本地保留，不随公开仓库发布）。

## 电脑侧可重复检查

从项目根目录运行，使用已有 Python 和 git：

```powershell
python -B docs/research/scripts/audit_minimal_routes.py
python -B -m unittest discover -s docs/research/scripts -p 'test*.py' -v
```

这两条不联网、不调用 ADB、不安装依赖；只校验/解析已有快照并生成评审材料。其他带 `root-readonly`
的采集脚本**会调用 ADB/su**，不要把它们混同于离线检查自动运行。

## 证据与发布边界

来源快照在 `evidence/`，机器可读结果在 `generated/`；这两个目录被 `.gitignore` 忽略，不随仓库发布。
公开仓库只发布 CI 代码、公开源码样例、补丁草案与对应说明，不发布设备证据、boot 镜像、分区数据或
主机状态。真实启动实验仍须遵守总路线中的红线与授权边界。
