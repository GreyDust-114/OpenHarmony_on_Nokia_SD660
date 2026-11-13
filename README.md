# OpenHarmony_on_Nokia_SD660

Nokia 7 Plus（B2N、Snapdragon 660）的 OpenHarmony 移植研究。

**目前没有可刷系统，也没有已验证可运行的 OpenHarmony 内核。手机仍用于短信接收/转发，不进行未经授权的重启、刷写或实验驱动部署。**

## GitHub Actions 单内核云编译

工作流仅手动触发：**Actions → Research kernel build (no flashing) → Run workflow**。

| 目标 | 内容 |
|---|---|
| `nokia44-baseline` | Nokia 社区 4.4 内核基线，建议首次选择，并行度 2 |
| `oh66-ft8716` | OH 6.6 通用 ARM64 内核及 FT8716 触摸补丁草案；没有 B2N 新设备树或完整面板适配 |

两者都是研究内核，**不是可直接刷写的 `boot.img` 或完整 OpenHarmony 系统**。工作流不连接手机、不自动创建 Release，只保存构建日志、配置和成功产物。

[构建步骤、资源/费用边界与失败日志说明](docs/cloud-build.md)。普通 runner 的磁盘空间有限，目前只规划单内核验证，不同步整套 OH 源码。

本仓库只上传云编译需要的脚本、补丁和说明，不需要上传手机凭据、vendor 二进制、短信或分区备份；本机研究证据保留在本地。

## 轻量验证

```powershell
python -B -m unittest discover -s ci -p 'test_*.py' -v
python -B ci/build_kernel.py --target nokia44-baseline
```

第二条只打印计划，不下载源码、不编译、不调用 ADB。实际云编译结果以 Actions 任务状态和日志为准。