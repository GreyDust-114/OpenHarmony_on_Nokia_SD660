# 第四轮：双路线最小改动清单与电脑侧验收

> 后续进展：已转为GitHub Actions构建，首次Nokia 4.4基线成功并完成[下载产物审查](archive/baseline-build-review.md)。本文中的“未编译”等描述保留第四轮当时状态；A0现已通过，但OH前置配置、token/HAL和实机验证仍未完成。
>
> **当前总路线与阶段计划已移到[移植总路线](port-roadmap.md)**（2026-11）：主路线收敛为 OH 7.0 Linux 标准系统 + B2N 6.6 内核 + 用户态 DRM VDI，Oniro hybris 降为后备。本文保留为双路线的详细工作项与历史推导。

## 当前结论

本轮开始把调研收敛为具体工作项，而非继续泛搜：

- **新内核路线已有一份可检查的FT8716补丁草案**：指定OH6.6提交上的2个文件、7行新增，电脑临时目录 `git apply --check` 通过。
- **旧内核路线可以分层验证**：基础Binder IPC、完整token身份、Android HAL隔离分别验收，不需要把整套Oniro 66文件补丁一次性搬入4.4。
- 面板是新路线的主要硬件工作之一。发现**65条两字节长包会被通用DCS写函数改成短包**，不能把原厂命令机械地翻译为同一种DRM helper调用。
- 现有HAL材料只能构建直接依赖图，不能假装已完成递归依赖或符号验证；后者是旧路线的明确阻塞项。

仍保留两条主候选，不宣布哪条已能启动，也不承诺总工期。

**本轮没有执行ADB、su、fastboot，没有查询或操作手机。** 只读取此前保存的实机证据、下载选定公开源码文件、生成电脑侧评审资料与运行测试；未下载完整系统、安装工具链或编译内核。

## 1. 本轮实际产物和检查结果

| 产物/检查 | 结果 | 不代表什么 |
|---|---|---|
| `drafts/ft8716-oh66-review.patch` | 6行驱动条目 + 1行DT binding，0行删除 | 不是完整B2N触摸移植，也不是可刷镜像 |
| patch应用检查 | 临时目录的固定源码上 `git apply --check` 通过 | 没有C编译、链接或实机测试 |
| FT8716代码路径比较 | OH6.6与v6.17的4个相关函数体忽略注释/无关空白后相同 | 没有验证硬件身份读取、reset/供电或固件 |
| 面板命令审查 | 重新从包记录重建120/2条命令，仍与源码一致 | 未发送任何面板命令 |
| HAL图 | 8个ELF、105条直接依赖边、37个依赖名称 | 37个依赖节点尚无递归ELF元数据，不是闭包 |
| 证据/源码校验 | 4份索引共98条记录的SHA256通过 | 只校验所列快照，不能校验未采集的设备状态 |
| 电脑测试 | 20项Python测试通过 | 不替代内核/DT schema/链接器/硬件测试 |

生成结果：

- `generated/minimal-route-audit.json`
- `generated/panel-packet-review.json`
- `generated/hal-dependency-frontier.json`

可重复的检查脚本：`scripts/audit_minimal_routes.py`，不包含联网或ADB功能。新增源码快照的URL和SHA256在`evidence/minimal-plan/index.json`；这轮20份快照不是完整可构建源码集。

### 电脑构建条件初查

另外只读查询了Windows磁盘/内存、PATH与WSL登记状态，没有启动发行版：

- 可见C盘剩余约 **58.2GiB**；D盘未报告可用空间，其他存储尚未核实。
- 物理可见内存约15.6GiB。
- 已登记`archlinux`与`Ubuntu-Embedded`，均为WSL2且查询时停止。
- Windows PATH找到Python/git/WSL，未找到Docker/Clang/CMake/Ninja。**这不说明WSL里没有这些工具**，本轮没有进入WSL检查。

Oniro已有文档给出的完整流程规划约150–180GB（见第一轮报告引用的BSP README），不是本项目的精确实测需求。按这个预算，当前不宜直接同步整套OH源码；先评估WSL内工具、虚拟磁盘实际空间和**单独内核/DT编译**的较小需求。未自动清理文件、扩容/迁移发行版或安装软件。

记录：`generated/host-preflight.json`、`generated/host-wsl-list.txt`。它们是主机状态快照，不在上述98条固定源码/实机证据校验记录内。

## 2. 共用先决条件：先锁定源码，不先生成启动镜像

### C0：版本/构建基线

当前仍有两个需要区别的版本事实：

1. Nokia社区内核为4.4.302，本机运行4.4.192；当前 `.config` 没有社区B2N配置中的 `CONFIG_FIH_ONYX`。不能把两者当成同一源码/配置。
2. 检查的OH6.6为镜像组织 `OpenHarmony-6.1-Release` 提交；Oniro manifest指定的GitCode `OpenHarmony-6.1-LTS` 并未证实与其一致。

**最小产物：** 每条路线一个单独版本清单，包括内核提交、设备配置、用户态manifest、补丁序列和编译器。当前研究快照不得冒充完整构建锁文件。[C1]

**验收：** 可重复获得相同输入；电脑环境和磁盘预算确认后，先做未改造基线构建。暂不安装工具、不下载整套源码。要进入完整编译，仍需先确定构建环境与资源预算。

### C1：共用的未来安全启动约束

boot v0式头部、64MiB boot分区与4.5GiB system/1GiB vendor是本机已采集参数，但DTB拼接位置、完整ramdisk、恢复路径与临时启动能力未验证。新Linux并不天然要求重分区或改成Volla布局，**也不因此保证原bootloader能加载它**。

任何真实测试之前，另行完成：个人数据迁出、短信替代机、可验证备份/恢复、实验rootfs不接触原userdata/NV的设计与授权。现在只进入电脑侧工作。

## 3. 路线A：Nokia 4.4 + OH + Halium/libhybris

### 最小工作清单

| ID | 最小改动/产物 | 依赖与验收 |
|---|---|---|
| A0 | 锁定能构建B2N的4.4源码、defconfig、DTB与模块组合 | C0；先证明未改内核可构建，不能直接用本机config覆盖社区配置 |
| A1 | 开启PID/UTS namespace；确定Binder四域/设备布局 | A0；kernel配置、launcher和init的设备路径必须一致 |
| A2 | 基础OH Binder最小程序的协议/映射/注册/调用测试设计 | A1；区分“能建立IPC”和“完整权限身份可用” |
| A3 | token设备 + task/fork生命周期 + Binder事务token传递 | A2；不删除权限校验，跨同步/异步/嵌套事务测试身份正确性 |
| A4 | 按真实feature位选择sender-info及其他扩展 | A3；未实现的功能不得谎报支持，处理不支持时的错误路径 |
| A5 | B2N Halium10用户态、匹配的libhybris兼容库和图形HAL运行集合 | 静态依赖闭包/符号/namespace审计；不能只复制EGL库 |
| A6 | 修改androidd/init/权限/graphics rc，启用composer和allocator桥接 | A1/A5；隔离OH与Android framework binder，分享预期的HIDL通道 |
| A7 | OH display/buffer VDI、EGL、MMI、存储账户服务的逐项接入 | A3/A6；不把测试图或基础shell称作完整OH桌面 |

### A1：不先强制回移植binderfs

已有Nokia源码支持多个静态Binder设备，Kconfig明确每个设备有独立context manager。可评估：

```text
OH framework IPC       -> binder
Android framework IPC  -> android-binder
Android HIDL桥接       -> hwbinder（预期共享）
Android vendor IPC     -> vndbinder（按HAL依赖共享）
```

这是一种候选设计，不是实测配置。选择静态第四设备就必须改Oniro对binderfs-control的预检、创建设备及路径绑定。若选择binderfs，则另列其回移植依赖，二者不要同时无目的地推进。`USER_NS`不是现有androidd clone列表的必需位；`DEVTMPFS`/`FHANDLE`是否启用取决于最终init/HAL方案，不直接照抄Mi A2全部配置。[A1]

### A2–A4：基础IPC与完整token身份分开

直接读取匹配LTS的OH IPC实现：[A2]

- `BinderConnector::OpenDriver()`先检查基础Binder协议；`BINDER_FEATURE_SET`失败时将feature置0，继续尝试mmap，而不是直接返回失败。
- `BinderInvoker`仅在支持相应feature时读取sender-info或access-token。
- `token_setproc.c`则直接通过`/dev/access_token_id`的ioctl读写自身token；设备缺失会返回无效ID或错误。[A3]

所以：**可以把基础IPC作为早期里程碑，但不能据此宣称完整OH权限体系无需内核改造。** 不应把返回0/UID回退当作绕过身份的解决方案。

最低token补丁的语义边界：

1. `task_struct`的token/first-token数据与初始化/派生规则；修改其布局可能影响现有外部`.ko`，要检查或重建匹配模块。
2. access-token设备的ABI、UID权限、输出结构初始化及生命周期。
3. Binder事务创建、送达、线程/嵌套调用中的身份传递；保持Android既有事务ABI兼容。
4. `BINDER_FEATURE_SET`和`BINDER_GET_ACCESS_TOKEN`等与用户态结构大小一致；不把实现了头文件宏当作已实现ioctl。
5. 暂缓非必须诊断/调度增强时，逐一记录上层依赖与错误处理，不盲目删功能。

例如Oniro X23补丁定义了sender-info宏，但该样本仅公布token位；OH IPC的sender-info位为bit2，有回退分支。OH6.6源码则已有sender-info实现及对应配置。这说明“宏存在”不等于4.4第一步就必须移入全部扩展。[A4]

冻结、内存诊断、thread reclaim等另列为功能验收项；部分调用有构建开关或错误回退，不能一概说“全部必须”，也不能一概说“全部可忽略”。完整桌面验收时需跟踪实际调用者。

**当前为什么不直接生成4.4 Binder补丁？** 运行内核、社区内核和Oniro参考补丁基线不同；现在只能给出语义改动范围。未先固定A0并核对ABI/锁/事务结构就机械生成补丁，会制造“补丁文件有了就能用”的错觉。

### A5–A6：HAL闭包的明确边界

现有记录能证明105条第一层依赖边的37个名称都有候选文件位置，**但37个依赖库本身都没有递归ELF元数据**。`/system/lib64`与`vndk-29`有多个候选，也还没按真实linker namespace判定采用哪个。[A5]

下一个最小产物不是拷贝清单，而是：

- 明确Android/Halium版本、compat库、VNDK/APEX与libhybris构建参数的一致性。
- 从获准的固件副本或以后单独的只读采集中获取依赖库元数据，计算递归闭包，检查SONAME、符号和版本。
- 对动态加载的EGL/HWC/gralloc/mapper插件和服务注册另作清单。
- 以匹配Android10环境验证QCOM/Pixelworks链路；旧rc的`onrestart restart surfaceflinger`不能原样进入精简HAL环境。
- 保持原始高通/Android接口行为。不能默认OH的feature ioctl可以由Android用户态理解，也不能混淆两边的framework binder。

本轮不再接手机，也没有原厂固件副本，因此递归闭包**明确未完成**，而不是把文件存在当作已经闭合。

## 4. 路线B：OH6.6 + 上游SD660栈 + B2N板级适配

### 最小工作清单

| ID | 最小改动/产物 | 依赖与验收 |
|---|---|---|
| B0 | 固定OH6.6基线与最小B2N DTS/启动方案 | C0；电源、reserved-memory、eMMC、USB、DTB打包先有依据 |
| B1 | FT8716 edt驱动+binding小型回移植 | **已有评审草案和apply检查**；下一步C编译与DT校验 |
| B2 | 新B2N触摸节点 | pinctrl/IRQ/reset/supplies/坐标；不能复制旧DT phandle数值 |
| B3 | FT8716U DRM panel：保序的命令、包类型、时序和状态机 | 120/2条已匹配；先解决65条短长包差异，再谈驱动运行 |
| B4 | NT50356/TI兼容偏压背光与面板/触摸电源协调 | 确认ID分支、供电供应者与冷启动/连续画面模式；不盲设电压 |
| B5 | 启用SD660 DRM/MSM和Adreno、组织固件、核验GPU/scanout buffer | 代码有支持不代表DTS/config已开启或本机运行正常 |
| B6 | OH DRM compositor/allocator、Mesa EGL/GLES接入 | PRIME/dma-buf/fence/格式/stride必须匹配，非简单链接libEGL |
| B7 | OH MMI设备映射与账户/存储服务集成 | 标准evdev是基础，不代表触摸权限/坐标已打通 |

### B1：可以独立评审的7行补丁

草案绑定到OH6.6镜像提交：`31c8f21f4c95d59c8e730038b868109e9244a936`，**不是任意6.6或Oniro manifest的通用补丁**。[B1]

对比四个函数体（忽略注释及无关空白）：

- `edt_ft5x06_ts_identify`
- `edt_ft5x06_ts_set_tdata_parameters`
- `edt_ft5x06_ts_isr`
- `edt_ft5x06_ts_set_regs`

与含FT8716支持的Linux v6.17一致。因此无需为了新增FT8716而整体换入v6.17驱动和新的debugfs等无关内核API；最小候选确实可先添加设备表/10点配置及binding。[B2]

这不覆盖probe供电/reset、硬件应答和PM。新DT还应解决：

- 旧`focaltech,fts`改为主线compatible；旧`focaltech,reset-gpio`等属性改为主线binding。
- 实机保存的GPIO数组首项162是旧DT内phandle，不是可照搬的硬件常数；新DT应引用自己的控制器标签。
- IRQ为GPIO67，触摸reset为66，但供电供应者与面板reset关系仍需完整板级依据。
- 旧evdev的X/Y最大值为1080/2160，而`touchscreen-size-*`是尺寸、通常导出max=size-1。不能未经核对就把旧坐标边界机械填为新尺寸；用测试确认边缘归一化。
- edt probe会主动控制regulator/reset，所以“加入条目”不等于可在当前Android上加载而不影响屏幕。**本项目现在不加载任何实验驱动。**

### B3：命令迁移已拆到包级，而不只复制payload

来自原厂编码器与OH6.6 DRM helper的差异：[B3]

| 原厂DT | 实际意义 | 通用`mipi_dsi_dcs_write_buffer()`风险 |
|---|---|---|
| `0x05`，如`11 00` | 无参数DCS，原厂只编码第一个命令字节 | 若直接按2字节传入，会变成带参数短写；需处理填充0 |
| `0x15`，2字节 | 单参数DCS短写 | 长度与类型吻合，但仍须保留LP/HS、延时 |
| `0x39`，2字节 | 明确的DCS长写 | 通用helper按长度2改发`0x15`；本机开屏序列中有**65条** |
| `0x39`，多于2字节 | DCS长写 | 类型吻合；仍须保留payload顺序和每包语义 |

生成的`panel-packet-review.json`保留原始type、payload、有效payload、VC/ACK/last、延时和helper类型差异。它是评审数据，不是重放程序。

不能随意在panel驱动调用`mipi_dsi_device_transfer()`：该函数在所查6.6源码中是文件内static。若要严格保留显式长包，需要设计可用的host-transfer封装并保留flag/错误处理，或明确验证面板接受短包等价语义；本轮未选定或验证任一种。

序列尾部也约束状态机：

- 第117条：sleep-out `0x11`，之后等120ms。
- 第118条：display-on `0x29`。
- 第119/120条：`0x35`、`0x53`设置。
- 关屏：`0x28`之后10ms，`0x10`之后150ms。

因此不能仅把`0x29`抽到另一个callback，忽略其后两条或重复发送。prepare/enable/disable/unprepare应有单一所有者、对称失败清理，并在host命令传输仍可用时完成关屏。先保留原序列相对顺序，再验证生命周期；显式命令等待合计不等于整个启动/关屏耗时。

### B4：背光不是简单的8位亮度函数

社区`mdss_dsi_panel_bklt_dcs()`对B2N FT8716U有专用路径：把0..255换算为0..1023，再拆为`value >> 2`与`value & 3`两个字段，经DCS `0x51`发送。不能直接替换成默认8位或默认16位大端亮度helper。[B4]

NT50356命名驱动还根据GPIO62区分TI/Novatek，并有使能、偏压和延时序列；部分GPIO配置为低而非简单“全部上电拉高”。原驱动未使用的init函数不属于实际最小启动流程。FT8716U的电源逻辑又受continuous-splash和double-tap分支影响，面板与触摸不能各自随意关闭共享电源。[B5]

这些代码来自社区基线，虽然DT开/关屏命令与本机匹配，**仍未证明原厂所有亮度/供电分支与其完全相同**。原始`.config`还启用了`CONFIG_PXLW_IRIS3`，HWC含Pixelworks依赖；驱动有`iris_is_valid_cfg()`分支。不能仅凭编译开关或库名断言物理IRIS在路径上，也不能假定它一定旁路。[B6]

B4验收前的剩余问题：实际偏压芯片分支、面板reset/供电供应者、是否存在有效IRIS配置/桥接路径。当前保留为阻塞项，不用写I2C、复位或开关电源来猜答案。

## 5. 决策门槛：下一步真正该验证什么

| 门槛 | 允许继续的证据 | 失败后的处理 |
|---|---|---|
| G0 输入锁定 | 两条路线各自源码/manifest/配置一致，电脑工具和资源确认 | 先解决版本，不编造可构建组合 |
| GA 旧路线最小内核 | 未改基线可构建；独立token/Binder改动能编译，ABI与模块依赖列明 | 若核心回移植失控，降低旧路线优先级 |
| GB 新路线驱动最小集 | FT8716驱动编译/DT校验通过；panel/bias状态机与包型问题可控 | 若需要未知显示桥/大规模供电逆向，降低新路线优先级 |
| GH 图形用户态 | A有可验证HAL依赖闭包；B有可编译DRM/EGL/buffer接口实现 | 不用“有驱动/有EGL库”替代证据 |
| GD 实机授权 | 数据/短信替代/恢复方案齐备，用户另行批准启动实验 | 继续电脑研究，不启动实验系统 |

**本轮已走到B1的静态apply门槛；尚未走过G0完整构建基线与任何硬件门槛。** 下一阶段最有价值的是检查现有WSL内部工具/空间并锁定源码，优先做单独内核/DT的编译验证，暂缓全量OH同步；不需要为了开始编译而修改手机。

## 6. 重复检查

在项目根目录，只使用电脑现有Python和git：

```powershell
python -B docs/research/scripts/audit_minimal_routes.py
python -B -m unittest discover -s docs/research/scripts -p 'test*.py' -v
```

审计脚本先校验快照，再生成JSON/补丁草案；git只做临时目录apply检查。脚本不会联网、安装依赖、调用ADB或运行vendor代码。测试覆盖证据篡改拒绝、补丁重复/失配拒绝、包型/填充/延时、依赖图边界和本地解析。

## 7. 直接来源

所有如下代码均来自维护方仓库或其Oniro镜像；新增源的精确URL和校验值在`evidence/minimal-plan/index.json`。

- [C1] [Nokia内核固定提交](https://github.com/nokia-msm8998/android_kernel_nokia_sdm660/tree/192f8b2a0a1bbb4042df16bdacd802a4321c5f53)；本机历史配置`evidence/device-kernel.config`；版本限制见[route-audit.md](archive/route-audit.md)。
- [A1] [Nokia Binder设备配置](https://github.com/nokia-msm8998/android_kernel_nokia_sdm660/blob/192f8b2a0a1bbb4042df16bdacd802a4321c5f53/drivers/android/Kconfig)；[Oniro LTS launcher](https://github.com/eclipse-oniro4openharmony/device_board_oniro/blob/e86d7bc152579cda2cb002d1e19357edb84d9c61/hybris_generic/launcher/androidd.c)。
- [A2] [OH IPC binder_connector.cpp](https://github.com/eclipse-oniro-mirrors/communication_ipc/blob/61d4cd7f72018e23a7b4e68c268b8f85dc5615e9/ipc/native/src/core/invoker/source/binder_connector.cpp)，同提交`binder_invoker.cpp`与`ipc/native/src/core/framework/include/sys_binder.h`。
- [A3] [OH token_setproc.c](https://github.com/eclipse-oniro-mirrors/security_access_token/blob/2da9dbc395ac5aa4f1974e4a554cd7c19eb5c388/interfaces/innerkits/token_setproc/src/token_setproc.c)。
- [A4] [Oniro X23内核补丁](https://github.com/eclipse-oniro4openharmony/device_board_oniro/blob/e86d7bc152579cda2cb002d1e19357edb84d9c61/hybris_generic/kernel/x23/patches/kernel-source/ohos-adaptation.patch)；[OH6.6 Binder](https://github.com/eclipse-oniro-mirrors/kernel_linux_6.6/blob/31c8f21f4c95d59c8e730038b868109e9244a936/drivers/android/binder.c)及同提交Kconfig/UAPI。
- [A5] 本机历史快照`evidence/root-probe/vendor-elf-metadata.json`与`vendor-dependency-locations.txt`，没有新设备读取。
- [B1] [OH6.6 edt驱动](https://github.com/eclipse-oniro-mirrors/kernel_linux_6.6/blob/31c8f21f4c95d59c8e730038b868109e9244a936/drivers/input/touchscreen/edt-ft5x06.c)及同提交binding。
- [B2] [上游FT8716支持提交](https://github.com/torvalds/linux/commit/c6f908f88a55be7641d78a99053818147bde93e9)，[v6.17驱动](https://github.com/torvalds/linux/blob/v6.17/drivers/input/touchscreen/edt-ft5x06.c)。
- [B3] [OH6.6 drm_mipi_dsi.c](https://github.com/eclipse-oniro-mirrors/kernel_linux_6.6/blob/31c8f21f4c95d59c8e730038b868109e9244a936/drivers/gpu/drm/drm_mipi_dsi.c)；[Nokia mdss_dsi_cmd.c](https://github.com/nokia-msm8998/android_kernel_nokia_sdm660/blob/192f8b2a0a1bbb4042df16bdacd802a4321c5f53/drivers/video/fbdev/msm/mdss_dsi_cmd.c)与同目录`mdss_dsi_host.c`；面板历史实机DT在`root-probe/live-dt-selected.json`。
- [B4] [Nokia mdss_dsi_panel.c](https://github.com/nokia-msm8998/android_kernel_nokia_sdm660/blob/192f8b2a0a1bbb4042df16bdacd802a4321c5f53/drivers/video/fbdev/msm/mdss_dsi_panel.c)。
- [B5] [Nokia偏压背光驱动](https://github.com/nokia-msm8998/android_kernel_nokia_sdm660/blob/192f8b2a0a1bbb4042df16bdacd802a4321c5f53/drivers/video/boost_nt50356.c)、同提交`mdss_dsi.c`。
- [B6] [Nokia IRIS配置分支](https://github.com/nokia-msm8998/android_kernel_nokia_sdm660/blob/192f8b2a0a1bbb4042df16bdacd802a4321c5f53/drivers/video/fbdev/msm/mdss_dsi_iris3_lightup.c)与[B4]的条件转发路径；只说明存在可选实现，不替代本机物理路径证据。
