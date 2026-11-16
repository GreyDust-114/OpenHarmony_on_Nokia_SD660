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

测试：CI 37 项（35 通过、2 项需本机 GCC 跳过），研究测试 35 项全通过。供电补丁在前三层补丁之上 `git apply --check` 通过，并断言应用后的 DTS/驱动与草案逐字节一致。

## 仍未做的

- 偏压寄存器编程的台架验证（默认关闭）。
- CABC/背光 DCS 亮度控制（原厂 `bl_ctrl_dcs`，1–255 级）。
- GPU/Adreno 启用与 SMMU 实际映射验证。
- 整机启动验证：目前仍是编译级产物。
