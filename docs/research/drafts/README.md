# 仅供评审的补丁草案

本目录不是可刷系统，不包含镜像或刷机脚本。没有将任何补丁部署到手机。

## FT8716 / OH6.6

`ft8716-oh66-review.patch` 的唯一基线是：

- 仓库：`eclipse-oniro-mirrors/kernel_linux_6.6`
- 分支快照：`OpenHarmony-6.1-Release`
- 提交：`31c8f21f4c95d59c8e730038b868109e9244a936`
- 驱动源码：`../evidence/minimal-plan/oh66-edt-ft5x06.c`
- binding：`../evidence/minimal-plan/oh66-edt-ft5x06.yaml`
- 原始URL与SHA256：`../evidence/minimal-plan/index.json`

基于Linux上游FT8716提交 [`c6f908f88a55be7641d78a99053818147bde93e9`](https://github.com/torvalds/linux/commit/c6f908f88a55be7641d78a99053818147bde93e9)（Jens Reidel，维护者Dmitry Torokhov合入）的语义，向上述OH6.6快照添加6行驱动条目；再参考Linux v6.17 binding补1行compatible。保持原驱动文件与binding的GPL许可，不冒称上游作者或测试者。

### 已检查

- 2个文件，7行新增、0行删除。
- 在一次性电脑临时目录中，对保存的原始文件运行 `git apply --check` 通过；没有应用到真实内核树。
- 指定OH6.6驱动与Linux v6.17的识别函数、报文布局函数、中断解析函数、寄存器选择函数，去除注释和无关空白后的函数体一致。
- 主机侧脚本/测试可以重复以上检查；快照校验失败时停止。

### 尚未检查

- C编译、链接、内核配置、`dt_binding_check` / `dtbs_check`。
- B2N新设备树、IRQ/reset/供电映射、实际触摸固件是否正常应答。
- 坐标最大值/size语义、休眠唤醒、手势、ESD恢复。
- 任何真实硬件运行。

补丁不包含B2N DTS，不是“七行就移植完整触摸”的结论。现有设备树的`focaltech,fts`也不会仅因为加入该补丁而自动匹配`focaltech,ft8716`。

复现只用电脑上已有Python与git，不联网、不调用ADB：

```powershell
python -B docs/research/scripts/audit_minimal_routes.py
python -B -m unittest discover -s docs/research/scripts -p 'test*.py' -v
```

脚本只生成评审材料，git检查使用临时源码文件。检查通过不等于编译成功，更不等于可安全启动。完整计划见 [minimal-port-plan.md](../minimal-port-plan.md)。

## B2N / OH6.6 DTS移植草案

`oh66-b2n.dts`以同一OH6.6源码树已有的`sdm660-xiaomi-lavender.dts`为结构模板，填入当前B2N硬件证据：

- `compatible = "nokia,b2n", "qcom,sdm660"`；
- PM660/PM660L公共include；
- `blsp_i2c4`、触摸地址`0x38`；
- IRQ GPIO67、reset GPIO66；
- touchscreen尺寸1080×2160；
- SDM660 pinctrl、MDSS/DSI/DSI PHY、Adreno、MMSS SMMU使用同版本公共树；本轮显示/GPU保持disabled，待面板供电补丁一起启用。
- GPIO67使用B2N旧DT/驱动一致的下降沿；GPIO66低有效，新增各自的GPIO pinctrl状态。

`oh66-b2n-dts-review.patch`将此草案安装为`arch/arm64/boot/dts/qcom/sdm660-nokia-b2n.dts`，并注册到qcom Makefile。独立目标`oh66-b2n-dts`先编译B2N及Lavender对照DTB，再核对二进制中的PMIC、I2C地址、GPIO phandle、IRQ类型和尺寸，随后编FT8716对象及Image.gz。

当前只做B2N DTS骨架，panel endpoint、FT8716U DRM panel和NT50356 provider单列为后续补丁。主线参考与逐项差异见[SDM660公开移植参考](../sdm660-open-source-references.md)。

OH6.6已包含`sdm660-xiaomi-lavender.dts`并在qcom Makefile注册。本轮沿用该版本公共include，仅新增B2N板级文件与Makefile条目；原有两个构建目标定义保持一致。

## OH6.6公共头文件准备

`oh66-common-headers-review.patch`原样保存自[固定的上游镜像补丁](https://github.com/eclipse-oniro-mirrors/kernel_linux_patches/blob/8183895af567d5f739af4fa7cf5856e608c4e046/linux-6.6/qemu-arm-linux_patch/oh_headers.patch)，SHA256为`9ecdd3593580a7cffb04595f23ba3df9fad3ced2699a87c32d9c13f6d8091b8d`。

这是后续云编译暴露`linux/xpm_types.h`缺失后加入的研究性构建支持，不是FT8716驱动补丁，也不是本次Release完整manifest的构建证明。内容仅涉及6个新增公共头文件及page-flags.h的3处宏调用参数修正；不含QEMU硬件/启动地址或watchdog改动。已通读并在固定OH6.6的page-flags.h快照及临时目录中通过git apply检查/应用；新增头文件与条件关闭分支保留原始实现和GPL声明，没有用自行编造的空头文件遮蔽缺失功能。后续编译/链接及运行行为仍须分别验证。

## OH6.6 KVM接口同步

`oh66-kvm-coalesced-sync-review.patch`只把固定OH6.6的`virt/kvm/coalesced_mmio.c`同步至Linux v6.6.101的对应文件（[固定提交](https://github.com/gregkh/linux/blob/3a8ababb8b6a0ced2be230b60b6e3ddbd8d67014/virt/kvm/coalesced_mmio.c)）。移除已由总线注销路径负责的重复销毁调用，并同步错误处理注释，没有关闭KVM或编译诊断。

已核对OH快照的`include/kvm/iodev.h`与该stable头文件完全相同，总线销毁/注销函数体也一致；调用处不同是#4失败的直接原因。`ci/fixtures/`保存小型公开源文件样例及出处，回归在临时Git树实际应用补丁，验证不再调用旧公共helper，且完整文件SHA256等于stable参考。它不替代真实C编译及运行测试。

## XPM页标志表条件同步

`oh66-xpm-mmflags-guard-review.patch`只将两个XPM表项从`IF_HAVE_PG_ARCH_X`改为源码中已有的`IF_HAVE_PG_XPM_INTEGRITY`，与`include/linux/page-flags.h`中枚举使用同一`CONFIG_SECURITY_XPM`条件。SHA256为`18cf10ee6c0e12d567bcd4f63cc439bce12dd77dd561531d969f430e11e758b3`。不更改配置开关或枚举位值。

公开源码样例及枚举摘录见`ci/fixtures/`。源合同回归覆盖XPM/架构标志四组合；Linux CI额外以HOST GCC编译同一最小宏/枚举矩阵，负对照必须重现原始未定义枚举错误。本机没有GCC，因此该C编译测试显式跳过，不将源码检查冒称C编译成功。
