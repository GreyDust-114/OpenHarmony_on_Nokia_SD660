# OH6.6＋FT8716：首次启动与依赖准备修复

## 运行记录

- [首次尝试 #2](https://github.com/GreyDust-114/OpenHarmony_on_Nokia_SD660/actions/runs/43608587825)：提交`d24f23e33ee1d2ed6a8bea25848ad49720b588e4`，失败于defconfig，尚未进入触摸驱动编译。
- [源码准备修复后 #3](https://github.com/GreyDust-114/OpenHarmony_on_Nokia_SD660/actions/runs/43610375857)：提交`549ccff5a9751ae4b4a1cd9c699e00ae68403ba0`。defconfig/olddefconfig通过；编译准备阶段缺少`linux/xpm_types.h`，任务失败，没有进入触摸驱动本体。
- [公共头文件支持后 #4](https://github.com/GreyDust-114/OpenHarmony_on_Nokia_SD660/actions/runs/43612680876)：提交`26e5d35e211d1360e1fb55ec1d1f12ef21b870ea`，目标`oh66-ft8716`、jobs=2。最终失败于完整Image的KVM子系统，但**FT8716对象编译已通过**。

- [KVM同步后 #5](https://github.com/GreyDust-114/OpenHarmony_on_Nokia_SD660/actions/runs/43617696112)：提交`472eead281599d02b01641876f75c02af2a0e2d6`，目标`oh66-ft8716`、jobs=2。KVM coalesced MMIO对象和FT8716对象均已通过；完整Image失败于XPM页标志调试表的条件宏错误。

- [XPM条件修复与诊断构建 #6](https://github.com/GreyDust-114/OpenHarmony_on_Nokia_SD660/actions/runs/43680269025)：提交`3d74d8c17d3a522fbe5347eea46240a4c5ecda72`，jobs=2，已触发。先在Linux CI验证真实C四组合及原始错误负对照，再执行OH6.6编译；完整镜像使用`make -k`收集独立错误，最终状态以任务页为准。

本轮没有ADB操作、手机改动、完整OH同步或本机内核编译。没有修改旧4.4目标，也没有改变FT8716补丁。

## 已抓到的确定失败

#2的源码拉取、提交核对、FT8716补丁检查/应用都成功。第一个失败点：

```text
*** Default configuration is based on 'defconfig'
fs/Kconfig:54: can't open file "fs/proc/memory_security/Kconfig"
```

失败artifact已保存在忽略目录`evidence/builds/run-43608587825/failure-artifact.zip`，只有诊断资料，没有成功内核镜像。

这不是“FT8716驱动编不过”的证据：当时Kconfig尚未完成解析。

## 判断与最小修复

核对的三个方向：

1. 漏拉外部源码：预测为内核仓库无对应目录、common_modules仓库有该模块。
2. 版本不匹配：预测为选择的common_modules提交不能提供内核引用的Kconfig/实现；必须固定并检查版本，不能随意使用master。
3. 目录未准备：即使下载外部仓库，没有映射到内核引用的位置也仍会出现相同错误。

直接源码确认：固定内核的`fs/Kconfig`引用该文件，而该目录不在单独内核checkout中；同Release分支的common_modules提供它及相应准备脚本。上游通过apply脚本将目录内容链接进内核树。

新增固定依赖：

- 仓库：`eclipse-oniro-mirrors/kernel_linux_common_modules`
- 分支研究参考：`OpenHarmony-6.1-Release`
- 提交：`4156fd1cc2f0ab6ab07102e8c1e92c79f644b5d3`

在defconfig之前，将五个真实模块子树复制到其Kconfig期望的位置：

| 外部模块 | 内核位置 |
|---|---|
| memory_security | fs/proc/memory_security |
| code_sign | fs/code_sign |
| dec | fs/dec |
| xpm | security/xpm |
| container_escape_detection | security/container_escape_detection |

这里只准备源码，没有删除Kconfig引用、创建空stub或关闭安全功能来使构建变绿。复制完整模块子树，与上游脚本目标目录一致；拒绝覆盖内核已有目录。依赖提交核对、准备路径和许可证进入artifact记录。没有执行外部apply脚本，也没有盲目套用仅面向5.10的新IP等无关准备逻辑。

这仍不是完整OH源码闭包或版本兼容性证明；后续编译若暴露其他依赖/接口问题，应继续按具体日志处理。

## 反馈与回归检查

快速回归命令：

```powershell
python -B -m unittest discover -s ci -p 'test_*.py' -v
```

修复前新加的契约测试确实变红：

```text
FAIL: test_oh66_declares_external_kconfig_sources
AssertionError: 0 != 1 : OH6.6 configuration requires pinned common_modules sources
```

修复后17项CI测试通过；新增文件布局测试验证原本缺失的`fs/proc/memory_security/Kconfig`会由真实源码填充，缺源时拒绝伪造stub，已有目录不会被覆盖，旧Nokia目标不会获得OH模块覆盖。

这是对源码准备逻辑的快速回归，而不是运行真正Kconfig编译器的替代。云任务#3已验证最初的Kconfig缺失问题确实解决，配置生成与合并均通过；后续失败是下面单独记录的公共头文件缺失，不把它误报成整个构建已经修好。

## 第二个阻塞点：公共头文件准备

#3在`arch/arm64/kernel/asm-offsets.s`准备过程中失败：

```text
include/linux/mm_types.h:22:10: fatal error: 'linux/xpm_types.h' file not found
```

镜像仓库内的Linux6.6源码直接引用该公共头文件，但独立checkout没有提供它。核对到`kernel_linux_patches`另一固定提交`8183895af567d5f739af4fa7cf5856e608c4e046`下已存在针对6.6的`linux-6.6/qemu-arm-linux_patch/oh_headers.patch`。

已通读并原样引入该补丁作为`docs/research/drafts/oh66-common-headers-review.patch`，SHA256为`9ecdd3593580a7cffb04595f23ba3df9fad3ced2699a87c32d9c13f6d8091b8d`。只添加6个公共头文件、修正page-flags.h中3处宏调用参数，不含ARM/QEMU启动地址、设备树、boot Makefile或watchdog改动。其公共头文件保留原始GPL声明和功能条件分支，没有自行编造空头文件遮蔽错误。

在固定OH6.6的page-flags.h源码快照及一次性临时目录中运行git apply检查/应用均通过；存在上游补丁自带的一处文件末尾空行警告，保持原文件与SHA一致没有私自改写。新增回归先因没有声明公共头文件支持而变红，再修复为18项CI测试通过；29项电脑研究脚本测试也通过。

这是从单独固定的上游镜像提交引入的研究性支持补丁，不是声称已经复现Release完整manifest。#4的真实日志已验证该准备步骤及FT8716对象编译通过；完整Image仍失败，原因如下。失败原件分别保存在本机忽略目录，不会上传设备证据。

## 第三个阻塞点：KVM调用处未同步总线销毁接口

#4的`29-compile-ft8716-object.log`以`CC drivers/input/touchscreen/edt-ft5x06.o`成功结束；后续`30-compile-kernel.log`首个error为：

```text
virt/kvm/coalesced_mmio.c:190:4: error: implicit declaration of function 'kvm_iodevice_destructor'
```

核对方向为缺少声明、配置条件和部分接口同步。实际发现：固定OH6.6的`include/kvm/iodev.h`与Linux v6.6.101完全一致；`kvm_io_bus_unregister_dev()`、`kvm_io_bus_destroy()`函数体也一致，已经负责设备销毁。只有coalesced MMIO调用处仍旧重复调用不再公开的helper，和同版本stable文件不同。不是触摸驱动错误，也不应靠重新加声明/空实现或关闭-Werror解决。

按[Linux v6.6.101固定提交](https://github.com/gregkh/linux/blob/3a8ababb8b6a0ced2be230b60b6e3ddbd8d67014/virt/kvm/coalesced_mmio.c)同步这一处，补丁`oh66-kvm-coalesced-sync-review.patch`的SHA256为`35aaa178a6dbf197f70bc88d44fd9e96fa39beab9b7251ca1960b7f9840209cc`。不关闭KVM，不降低诊断，也不修改FT8716补丁或旧4.4目标。

回归在真实固定源码样例上应用声明的补丁，修复前红于`KVM caller still uses retired helper and duplicates bus-owned destruction`，修复后输出文件SHA256为`414f9b16edb7fd8562af7730ccdf47f6278c1b5ac17dcde46748b7f091fa8ffb`，与完整stable参考文件一致。临时Git树显式关闭autocrlf以保证Windows/Linux一致，未修改全局Git配置。19项CI测试、29项研究脚本测试通过。该回归是源代码/补丁检查，不冒称已本机编译C代码；完整云端编译仍须另行验证。

预防：补入稳定版接口变更时必须同时核对提供者、所有调用者以及析构所有权；不能只补回缺失函数来消除编译报错。

## 第四个阻塞点：XPM枚举与调试表使用不同配置条件

#5最终失败日志已保存在本机忽略目录`evidence/builds/run-43617696112/`。真实输出包含`CC ...coalesced_mmio.o`、`AR arch/arm64/kvm/built-in.a`及FT8716对象成功；新的首个错误是`mm/debug.c`展开调试表时未定义`PG_xpm_readonly`、`PG_xpm_writetainted`，后续sizeof不完整数组错误是连带结果。

检查了错误条件宏、枚举不同步、配置未保留三个方向。固定源码的枚举和`IF_HAVE_PG_XPM_INTEGRITY`定义都按`CONFIG_SECURITY_XPM`控制，但两个表项误用了`IF_HAVE_PG_ARCH_X`。本轮配置中架构条件为y、XPM没有定义，因而输出了不存在的枚举；反向组合也会漏项。

`oh66-xpm-mmflags-guard-review.patch`仅替换这两个调用，SHA256为`18cf10ee6c0e12d567bcd4f63cc439bce12dd77dd561531d969f430e11e758b3`。没有开关XPM、关闭安全功能、改动枚举值或降低编译检查。

断点前已运行真实固定源码的四组合源合同回归：修复前`XPM=false/ARCH=true`和`XPM=true/ARCH=false`两种组合变红；修复后通过。测试还包含Linux HOST GCC最小C编译矩阵及原始源码的负对照，本机无GCC所以明确跳过该项，待云CI实测。断点前完整本地结果为22项CI测试中21通过、1跳过，另29项研究测试通过，不能称为已通过C编译矩阵或完整内核构建。

本轮将OH6.6完整镜像命令改为`make -k ... Image.gz`，让独立错误在一轮中尽量暴露；仍保持非零退出码、完整错误日志和120分钟上限。不改变配置/触摸对象的快速失败，也不影响旧4.4目标。后续先看C矩阵和诊断构建的实际结果，再决定如何处理剩余基线问题，不盲目连续重跑。

恢复后发布提交`3d74d8c17d3a522fbe5347eea46240a4c5ecda72`并启动#6；GitHub API已确认Linux runner的“Validate CI code and print the build plan”成功。该步骤会运行真实HOST GCC四组合和原始错误负对照；缺少GCC时在Actions环境直接失败而非跳过。因此C矩阵的云端验证已通过，完整内核构建此时仍在运行，不能据此宣称Image成功。

## 来源

- [固定内核fs/Kconfig](https://github.com/eclipse-oniro-mirrors/kernel_linux_6.6/blob/31c8f21f4c95d59c8e730038b868109e9244a936/fs/Kconfig)
- [固定内核security/Kconfig](https://github.com/eclipse-oniro-mirrors/kernel_linux_6.6/blob/31c8f21f4c95d59c8e730038b868109e9244a936/security/Kconfig)
- [固定common_modules源码](https://github.com/eclipse-oniro-mirrors/kernel_linux_common_modules/tree/4156fd1cc2f0ab6ab07102e8c1e92c79f644b5d3)
- 同一common_modules提交下的`memory_security/apply_hideaddr.sh`、`code_sign/apply_code_sign.sh`、`dec/apply_dec.sh`、`xpm/apply_xpm.sh`、`container_escape_detection/apply_ced.sh`；均已直接阅读。

预防：后续单独抽取OH内核进行CI时，外部Kconfig源码准备也是构建输入的一部分，不能只验证触摸补丁能否应用。
