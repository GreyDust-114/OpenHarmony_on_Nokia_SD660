# OH6.6 显示供电链路：PM660 L11 + NT50356 偏压

## 这轮补的是什么

真机 415I 设备树暴露出一个真实缺口：B2N 的 OH6.6 DTS 只引了 `sdm660`/`pm660`/`pm660l` 三个 dtsi，**没有任何 PMIC regulator 定义**（Lavender 有，我们没有抄）。所以面板 1.8V I/O 供电和偏压链路此前都是断的。

这轮把显示供电整条链补上。

## 面板 I/O 供电

原厂 415I：`dsi_panel_pwr_supply` 只有一路 `wqhd-vddio`，来自 **PM660 L11，1.8V**，enable load 32mA。

实现：

- DTS 增加 `&rpm_requests { regulators-1 { … } }`，定义 `vreg_s4a_2p04: s4` 与 `vreg_l11a_1p8: l11`（1.78–1.95V），并补上父级 `vdd_l8_l9_l10_l11_l12_l13_l14-supply = <&vreg_s4a_2p04>` 与 `vdd_s4-supply = <&vph_pwr>`。
- 根节点增加 `vph_pwr` 固定 3.7V regulator，作为 PMIC 输入。
- 面板节点新增 `vddi0-supply = <&vreg_l11a_1p8>`。
- 面板驱动新增可选 `vddi0` 供电：`prepare` 先 enable 再拉 reset；初始化失败或 `unprepare` 后 disable。缺该属性时只告警，不阻止其它板子复用驱动。

## NT50356 偏压

原厂事实（415I DTB + 公开 Nokia 厂商驱动）：

| 项目 | 值 |
|---|---|
| 位置 | `i2c7`（`i2c@c1b7000`）地址 `0x11` |
| compatible | `novatek,nt50356`（兼容 TI LM36274，由 ID 脚区分） |
| HWEN | GPIO13 |
| ENP | GPIO35 |
| ENN | GPIO48 |
| ID | GPIO62（输入，0=TI / 1=Novatek） |
| bias 码 | avdd 0x20 / avee 0x20 |

新驱动 `drivers/regulator/nt50356.c`：

- 注册 `novatek,nt50356` I2C 驱动，取 bl-en/enp/enn/id 四个 GPIO 和 regmap。
- 上电顺序严格按厂商：HWEN → ENP → ENN，每步 2ms；下电反向。
- **寄存器 bias 编程默认关闭**，只有 DTS 写明 `novatek,program-bias` 才执行：`0x09=0x28` → `0x0D=avdd` → `0x0E=avee` → `0x09=0x9E`。
- 原因：厂商驱动里有两套互斥分支（TI / Novatek），且它写的 bias 码（0x24）与设备树值（0x20）不一致。在台架验证前，用猜的电压码去驱动面板有损坏风险，所以默认只跑 GPIO 时序，这也正是首次点亮需要的部分。

## 构建与验收

- 新增 `CONFIG_REGULATOR_NT50356`，注册进 `drivers/regulator/{Kconfig,Makefile}`。
- CI 目标新增 `bias_object_target`（`drivers/regulator/nt50356.o`），编译顺序在 panel 之后、Image 之前。
- 配置验收要求 `CONFIG_REGULATOR=y`、`CONFIG_REGULATOR_NT50356=y`。
- 最终 `System.map` 链接验收新增 `nt50356_driver`。
- DTB 新增 `b2n-display` 契约检查（与 `b2n-touch` 并行）：
  - 面板 compatible 唯一、`reg = 0`、`reset-gpios` = GPIO53 低有效；
  - `vddi0-supply` 能解析到实际 regulator 节点，且 `regulator-min-microvolt = 1780000`；
  - 偏压节点唯一、I2C 控制器 MMIO `0xc1b7000`、地址 `0x11`；
  - bl-en/enp/enn/id 四个 GPIO 引脚号正确。

测试：CI 40 项（38 通过、2 项需本机 GCC 跳过），研究测试 35 项全通过。供电补丁在前三层补丁之上 `git apply --check` 通过，并断言应用后的 DTS/驱动与草案逐字节一致。

## 首次云构建失败与修复：#16 的 DTS 语法错误

[任务 #16](https://github.com/GreyDust-114/OpenHarmony_on_Nokia_SD660/actions/runs/43830761269)（提交 `12e5864`）在真实 DTB 编译阶段失败，尚未进入内核 C 编译：

```text
arch/arm64/boot/dts/qcom/sdm660-nokia-b2n.dts:25.10-27 syntax error
FATAL ERROR: Unable to parse input tree
```

原因不是 label 缺失或驱动代码：供电补丁第一个 hunk 多插入了一个 `};`，先在 `chosen` 之后关闭根节点，再把 `vph_pwr` 节点写在文件顶层。DTS 顶层只允许 `/dts-v1/` 等指令和 `&label { }` 引用块，节点定义必须在根节点或引用块内部，所以 dtc 在 `vph_pwr:` 这一行报语法错误。同轮 Lavender 对照 DTB 正常，问题只在 B2N 板级 DTS 的组合结果。

修复只调整该 hunk 的节点位置，把 `vph_pwr` 放回根节点 `/ { }` 内；3.7V 固定输入与 `vdd_s4-supply` 引用的语义不变。补丁长度仍为 11,538 字节，SHA256 从 `e2474255…54dbc76` 变为 `3b38b531…599b78fbd`，manifest 已同步。

本机用真实 `cpp`/`dtc` 对固定提交 `31c8f21` 的稀疏检出做了对照（Windows + WSL，不是 CI 的替代品）：

- 修复前：复现同一个 `25.10-27 syntax error`，行号与云端一致；
- 修复后：B2N DTB 编译通过（44,090 字节），Lavender 对照 47,317 字节与 #14 产物相同；
- 真实 B2N DTB 通过 `b2n-touch`/`b2n-display` 契约：`vddi0-supply` 解析到 `/remoteproc/glink-edge/rpm-requests/regulators-1/l11`（1,780,000µV），NT50356 位于 `/soc@0/i2c@c1b7000/nt50356@11`，bl-en/enp/enn/id 四个 GPIO 全部匹配。

新增回归：`ci/device_tree.py` 的 `check_dts_layout()` 检查组合后的板级 DTS 是否把所有节点放在根节点或 `&label` 引用块内；`ci/test_b2n.py` 覆盖合法与非法布局，`test_display_power.py`、`test_display_link.py` 对真实组合结果调用该检查。回归在旧补丁下于 line 25 变红（与 dtc 报错行一致），修复后 40 项 CI 测试中 38 通过、2 项因本机无 GCC 跳过。

这是本地 DTS 语法/布局复现，不是把内核编译搬回本机；完整内核编译仍只在一次性 runner 上执行。

## 仍未做的

- 偏压寄存器编程的台架验证（默认关闭）。
- CABC/背光 DCS 亮度控制（原厂 `bl_ctrl_dcs`，1–255 级）。
- GPU/Adreno 启用与 SMMU 实际映射验证。
- 整机启动验证：目前仍是编译级产物。
