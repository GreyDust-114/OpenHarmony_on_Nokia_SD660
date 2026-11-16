# B2N 面板硬件适配：命令、时序和供电映射

## 本轮范围

从 #14 已完成链接的底座，改为 B2N 原厂 FT8716U 初始化序列、完整 mode 和面板 reset。NT50356 的 regulator/backlight 驱动仍单独实现，本轮不凭设备名推断实际芯片。

手机最初为unauthorized，随后获得普通ADB授权。已确认B2N_sprout/SDM660和I2C7/0x11的nt50356驱动绑定。面板信息和设备树属性返回Permission denied，已停止；未执行su、重启、设置更改、I2C直接访问、输入事件读取或刷写。原始查询结果仅保存在忽略的本地evidence/panel-adaptation/目录。本轮代码仍以既有原厂公开源码为依据，root只读补采集需另行确认具体范围。

## 原厂 FT8716U 配置

主证据：`evidence/hardware-audit/nokia-ft8716u-panel.dtsi`，公开 Nokia 内核固定来源与前期索引保持一致。公开测试副本：`ci/fixtures/nokia-b2n-ft8716u-panel.dtsi`。

- 第27–37行：1080×2160、60Hz，水平前肩/后肩32/32，脉宽2；垂直16/16，脉宽2。
- 第46–182行：on命令流120包；含65条长度2的0x39长写，不能用根据长度自动选型的DCS写helper代替。
- 第183–186行：off命令2包；display-off后10ms、sleep-in后150ms。on中的sleep-out后120ms。
- 第189–197行：on=LP，off=HS，sync pulse、burst video、LP11 init、init delay 5us。
- 第206–211行：reset物理电平序列1/0/1，保持1/1/10ms；物理尺寸68×136mm。
- 第214行：TX EOT append，不应继承参考驱动的NO_EOT_PACKET。
- 第266–268行：DSI0 panel reset为GPIO53，TE为GPIO59，触摸reset另为GPIO66。
- 第278–285行：原厂panel I/O为PM660 L11、1.8V；供电实现需与NT50356 bias顺序一起接入。

行号用于导航，以属性名和值为准；代码注释有条件编译与旧内容，不等同于所有分支都在实际运行。

## 传输实现

`drafts/oh66-b2n-ft8716u-commands.h`由`generate_b2n_panel_commands.py`从公开DTS剔除注释后生成，保留每个7字节Qualcomm头及payload。传输函数逐包显式填写mipi_dsi_msg.type/channel/flags/tx_len/tx_buf，调用OH6.6已有host->ops->transfer。

API依据：固定OH6.6的`drivers/gpu/drm/drm_mipi_dsi.c:444–455`私有helper也调用同一个host op；其公开DCS helper会按长度选择类型。本实现显式传LP/HS，不修改全局mode_flags。原始last=1被约束为独立消息；拒绝不支持的类型、channel、batch、长度。传输错误立即停止，短传输报EIO，延时只在成功后执行。

面板reset采用GPIO_ACTIVE_LOW描述符：原厂物理1/0/1映射为逻辑0/1/0。DTS改为`nokia,b2n-ft8716u`，避免让B2N初始化命令匹配到其他FT8716U面板。

## NT50356 / LM36274 GPIO职责

`evidence/route-audit/nokia-boost_converter_nt50356_i2c_0x11.dtsi`的活动`i2c_7`节点（第20–31行）给出：

| GPIO | 原厂属性 | 职责 |
|---|---|---|
| 13 | novatek,bl-en-gpio | boost/backlight HWEN |
| 35 | novatek,enp-gpio | ENP |
| 48 | novatek,enn-gpio | ENN |
| 62 | novatek,id-gpio | 芯片分支识别输入，不是panel reset |
| 53 | DSI0 platform-reset-gpio | FT8716U panel reset |
| 66 | fih,tp-reset-gpio | 触摸reset |

`evidence/hardware-audit/nokia-boost_nt50356.c:290–291`读取ID GPIO并标注0=TI、1=Novatek；第406–412行明确将ID线设为input。第106–192行存在条件编译的NT50356/LM36274初始化寄存器分支。因此compatible字符串本身不能证明实际焊接芯片。

后续补采集仅需确认：现有驱动绑定、ID GPIO元数据/状态、当前选中的面板节点与供电引用。不得为了识别芯片执行i2cdetect/i2cget、debugfs寄存器读写或翻转GPIO。root调试接口查询应先说明路径和范围。

## 验证

- Patch回归按board → display-link → hardware顺序在临时Git树应用，检查最终驱动/header与草案相同，DTS使用GPIO53和B2N专用compatible。
- header与公开原厂DTS逐字节对比；包数、65条长写和延时单独断言。
- Linux CI以GCC编译实际传输函数的host mock harness，执行完整on/off并逐包核对类型、padding、flags、长度与delay；检查负错误、短传输、截断和非法header停止行为。本机无GCC时明确跳过，不安装工具。
- 保留旧的最终System.map链接验收和DTB触摸验收。
- 本轮供电实现未完成，无实机亮屏测试。
