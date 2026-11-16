# OpenHarmony on SD660 / Nokia 7 Plus

研究目标：在Nokia 7 Plus（B2N、SD660）上探索OpenHarmony原生启动、显示和触摸。

**当前没有可刷系统。手机仍用于短信接收/转发，禁止未经授权的重启、刷写或实验驱动部署。** 已有的硬件取证为用户授权的只读查询。

## 用GitHub Actions编译，不占本机大磁盘

已准备[手动云编译流程](docs/cloud-build.md)，可选目标：

- `nokia44-baseline`：Nokia社区4.4内核基线。
- `oh66-ft8716`：OH6.6通用arm64内核与FT8716触摸补丁草案。
- `oh66-b2n-dts`：B2N板级DTS/显示/触摸/供电补丁，产出B2N DTB与`Image.gz`。
- `oh66-b2n-boot`：在上一目标基础上打包**仅供`fastboot boot`内存启动的研究启动镜像**（boot v0 + 最小initramfs），用于真机K1验证，不可刷写。

在仓库默认分支放入工作流后，到 **Actions → Research kernel build (no flashing) → Run workflow** 选择一个目标。建议先运行旧内核基线，并行度2。启动镜像只用于临时内存启动，不写任何分区；真机实验需遵守[移植总路线](docs/research/port-roadmap.md)中的授权与红线。

首次Nokia 4.4云编译已成功，产物完整性、ARM64 Image及B2N板级DTB已核对；B2N DTB/显示/供电目标已在云CI完成编译、契约与链接验证（[#17](https://github.com/GreyDust-114/OpenHarmony_on_Nokia_SD660/actions/runs/43833334992)），K1研究启动镜像已在[#18](https://github.com/GreyDust-114/OpenHarmony_on_Nokia_SD660/actions/runs/43852272454)成功打包（[启动镜像与K1准备](docs/research/b2n-boot-bringup.md)）。**OH6.6目标仍只是编译级产物，真机启动/显示/触摸尚未验证。**产物不是刷机包；完整OH构建的空间仍需按实际runner另行规划。

无需上传实机证据、vendor库、分区备份或手机凭据。`.gitignore`默认保护本机采集记录；公开仓库前仍须人工检查。[最小上传文件清单与费用/空间说明](docs/cloud-build.md)。

## 研究资料

- [研究索引与各轮证据](docs/research/README.md)
- [两条路线的最小改动与验收门槛](docs/research/minimal-port-plan.md)
- [FT8716补丁草案说明](docs/research/drafts/README.md)

## 本机只做轻量检查

```powershell
python -B -m unittest discover -s ci -p 'test_*.py' -v
python -B ci/build_kernel.py --target nokia44-baseline
```

第二条只打印计划，不下载源码、不调用编译器或ADB。带实机证据的研究审计仍在本地单独运行，不是云CI前提。
