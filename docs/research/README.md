# Nokia 7 Plus / SD660 OpenHarmony 研究索引

## 当前状态

目标：原生启动、显示、触摸；暂不追求完整手机功能。

约束：手机仍保存个人数据并承担短信接收/转发，禁止修改或中断现有系统。第三轮经用户授权使用现有su只读；第四轮未再操作手机。没有刷机、重启、切槽或部署实验驱动。

**最新验证结果：[B2N 显示供电构建审查](oh66-b2n-power-build-review.md)。** 云CI已编译并通过二进制契约：B2N DTB（PM660 L11面板1.8V与NT50356偏压节点）、panel与bias对象、显示/供电驱动链接、有效ARM64 `Image.gz`；仍是编译级产物，没有上机运行。后续工作清单仍见[minimal-port-plan.md](minimal-port-plan.md)。

- 两条主候选：旧4.4 + OH/Halium/libhybris；OH6.6 + 上游SD660驱动 + B2N适配。
- 已产出[FT8716评审草案](drafts/README.md)与B2N板级/显示/供电补丁，均已通过云CI编译与链接；未在手机运行。
- 已有面板包级审查和HAL第一层依赖图；尚未证明显示驱动在B2N上实际出图、HAL或OH桌面可运行。
- 主机已登记WSL2，C盘空间不足以直接规划全量OH；现已转为[GitHub Actions单内核云编译](../cloud-build.md)。已推送最小CI文件并成功完成首次Nokia 4.4云构建；本机只检查小产物，没有安装或清理构建环境。

## 各轮资料

1. [第一轮可行性基线](feasibility.md)：只读shell信息、候选架构与风险。
2. [第二轮源码路线审计](route-audit.md)：现代SD660驱动、Oniro图形与内核适配。
3. [第三轮root实机证据](root-hardware-and-routes.md)：FT8716U/FT8716变体、面板序列匹配、启动头和HAL元数据。
4. [第四轮最小改动与门槛](minimal-port-plan.md)：两条工作清单、FT8716草案、DSI类型差异、Binder功能分层。
5. [GitHub发布与首次任务](github-publication.md)：最小上传边界、保留初始历史、任务链接。
6. [首次基线产物审查](baseline-build-review.md)：ZIP及GitHub digest匹配、有效ARM64 Image、10个DTB、配置与日志限制。
7. [OH6.6云端尝试](oh66-cloud-run.md)：FT8716、KVM对象编译已通过；任务#7生成了有效generic ARM64 `Image.gz`，配置与限制详见[OH6.6产物审查](oh66-build-review.md)。
8. [SDM660公开移植参考](sdm660-open-source-references.md)：主线SDM660多设备DTS、Jasmine板级结构、FT8716U DRM panel/binding和下一步B2N适配表。
9. [B2N DTS草案](drafts/oh66-b2n.dts)：采用OH6.6同版本Lavender结构与公共SoC/PMIC树，已接入独立`oh66-b2n-dts`云目标及编译后二进制属性检查；任务链接见[运行记录](oh66-cloud-run.md)。
10. [B2N DTS构建审查](oh66-b2n-dts-build-review.md)：B2N/对照DTB、I2C4/FT8716/GPIO66/67/1080×2160合同、触摸对象和Image.gz均已完成。
11. [B2N显示内建链接审查](oh66-b2n-display-build-review.md)：MSM/MDP5/DSI/14nm PHY/panel全部内建，System.map三个显示符号通过（#14）。
12. [B2N面板硬件适配](b2n-panel-hardware-adaptation.md)：原厂120/2包命令流、timing、GPIO53 reset与传输实现（#15）。
13. [B2N显示供电与偏压](oh66-display-power.md)：PM660 L11面板1.8V、NT50356 GPIO时序；#16布局失败与修复、#17构建结果见[供电构建审查](oh66-b2n-power-build-review.md)。

后轮会修正/细化前轮结论，前轮的权限与证据范围仅描述当时状态。

## 电脑侧可重复检查

从项目根目录运行，使用已有Python和git：

```powershell
python -B docs/research/scripts/audit_minimal_routes.py
python -B -m unittest discover -s docs/research/scripts -p 'test*.py' -v
```

这两条不联网、不调用ADB，不安装依赖；只校验/解析已有快照并生成评审材料。其他带`root-readonly`的采集脚本**会调用ADB/su**，不要把它们混同于离线检查自动运行。

来源快照在`evidence/`，机器可读结果在`generated/`。没有镜像或可安全刷写的产物；真实启动实验仍需独立的数据/短信替代/恢复准备和用户授权。
