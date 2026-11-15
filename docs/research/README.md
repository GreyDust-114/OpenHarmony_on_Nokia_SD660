# Nokia 7 Plus / SD660 OpenHarmony 研究索引

## 当前状态

目标：原生启动、显示、触摸；暂不追求完整手机功能。

约束：手机仍保存个人数据并承担短信接收/转发，禁止修改或中断现有系统。第三轮经用户授权使用现有su只读；第四轮未再操作手机。没有刷机、重启、切槽或部署实验驱动。

**最新验证结果：[Nokia 4.4基线构建审查](baseline-build-review.md)。** 旧内核A0编译门槛已通过，GitHub产物digest、内部校验和B2N DVT/QC设备树已核对；尚未启动手机或集成OH。后续工作清单仍见[minimal-port-plan.md](minimal-port-plan.md)。

- 两条主候选：旧4.4 + OH/Halium/libhybris；OH6.6 + 上游SD660驱动 + B2N适配。
- 已产出[FT8716评审草案](drafts/README.md)，只做了静态检查与临时目录apply检查，未编译/运行。
- 已有面板包级审查和HAL第一层依赖图；尚未证明显示驱动、HAL或OH桌面可运行。
- 主机已登记WSL2，C盘空间不足以直接规划全量OH；现已转为[GitHub Actions单内核云编译](../cloud-build.md)。已推送最小CI文件并成功完成首次Nokia 4.4云构建；本机只检查小产物，没有安装或清理构建环境。

## 各轮资料

1. [第一轮可行性基线](feasibility.md)：只读shell信息、候选架构与风险。
2. [第二轮源码路线审计](route-audit.md)：现代SD660驱动、Oniro图形与内核适配。
3. [第三轮root实机证据](root-hardware-and-routes.md)：FT8716U/FT8716变体、面板序列匹配、启动头和HAL元数据。
4. [第四轮最小改动与门槛](minimal-port-plan.md)：两条工作清单、FT8716草案、DSI类型差异、Binder功能分层。
5. [GitHub发布与首次任务](github-publication.md)：最小上传边界、保留初始历史、任务链接。
6. [首次基线产物审查](baseline-build-review.md)：ZIP及GitHub digest匹配、有效ARM64 Image、10个DTB、配置与日志限制。
7. [OH6.6云端尝试](oh66-cloud-run.md)：FT8716与KVM对象编译已通过；完整Image失败于XPM调试表条件宏，修复后已启动带四组合C回归的诊断任务#6，镜像仍待验证。

后轮会修正/细化前轮结论，前轮的权限与证据范围仅描述当时状态。

## 电脑侧可重复检查

从项目根目录运行，使用已有Python和git：

```powershell
python -B docs/research/scripts/audit_minimal_routes.py
python -B -m unittest discover -s docs/research/scripts -p 'test*.py' -v
```

这两条不联网、不调用ADB，不安装依赖；只校验/解析已有快照并生成评审材料。其他带`root-readonly`的采集脚本**会调用ADB/su**，不要把它们混同于离线检查自动运行。

来源快照在`evidence/`，机器可读结果在`generated/`。没有镜像或可安全刷写的产物；真实启动实验仍需独立的数据/短信替代/恢复准备和用户授权。
