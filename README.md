# SDT 网络设备巡检

一个 Windows 桌面程序，用于批量登录 **SDT 设备**（SSH / Telnet），自动执行巡检命令并将结果保存为日志。本程序是 SDT 设备专用巡检程序。

<img width="1242" height="812" alt="image" src="https://github.com/user-attachments/assets/a30f331d-da7e-4ac3-9ecb-c7b829a7b617" />



> 本仓库**仅分发编译后的程序**，源代码不公开。
>
> **本程序是 SDT 设备专用巡检程序**，仅适用于 SDT 系列设备的巡检场景。

## 功能特性

- **并发巡检**：1–50 台并发（默认 5），基于线程池
- **协议支持**：SSH（Paramiko）/ Telnet（Netmiko），按设备类型自动选择驱动
- **设备类型可配置**：驱动、命令文件、分页禁用命令、是否需要 enable
- **实时搜索**：按设备名 / IP / 类型 / 协议 / 端口 过滤列表，不改变选中状态
- **定时巡检**：每天 / 每周 / 每月，指定时间自动执行，展示下一次运行时间
- **SSH 主机密钥**：默认兼容旧 SDT（自动接受未知密钥），可开启严格校验
- **结果日志**：每台设备独立文件，按天归档，密码以 `****` 脱敏

## 下载与运行

1. 在 [Releases](../../releases) 页面下载最新版本的压缩包（如 `sdt_inspection_win64.zip`）。
2. 解压到任意目录。
3. 双击 `sdt_inspection.exe` 启动。首次启动会在同级目录自动生成 `config/` 示例配置。

> 本程序为 Windows 平台打包（onedir 模式），无需安装 Python 运行环境。

## 配置

首次启动会在程序目录生成示例配置，按需修改即可。

### 设备列表 `config/devices.csv`

兼容两种格式：

- 6 列（原版 SDT）：`设备名,IP地址,用户名,密码,协议,端口`
  ```
  SDT-Device-01,192.168.1.101,admin,password123,telnet,23
  ```
- 8 列（带设备类型）：`设备名,IP地址,设备类型ID,用户名,密码,enable密码,端口,协议`
  ```
  核心设备,192.168.1.1,sdt,admin,password,,23,telnet
  ```

协议为空时使用设备类型的默认协议。文件编码支持 UTF-8、GB18030、GBK、GB2312、Big5。

### 设备类型 `config/device_types.csv`

```text
类型ID,名称,SSH驱动,Telnet驱动,是否需要enable,禁用分页命令,默认协议,命令文件路径
sdt,SDT设备,paramiko,generic_termserver_telnet,0,,telnet,commands/commands_sdt.txt
```

命令文件路径相对于 `config` 目录。

### 命令文件 `config/commands/commands_sdt.txt`

每行一条命令，`#` 开头的行会被忽略：

```text
display version
show running-config
```

## 界面说明

- **顶部操作区**：开始 / 停止 / 加载配置 / 并发数 / 输出编码
- **统计卡片**：总计 / 成功 / 失败 / 进行中
- **设备列表**：支持全选、反选、单设备勾选、实时搜索
- **定时巡检条**：开启开关后选择 每天 / 每周 / 每月 及时间，右侧显示下一次执行时间
- **运行日志**：实时彩色日志面板

## SSH 主机密钥校验

默认允许自动接受未知主机密钥（兼容旧 SDT）。生产环境建议开启严格校验：

1. 工具栏勾选“严格主机密钥校验”
2. 或通过环境变量启动：
   ```powershell
   $env:SDT_STRICT_HOST_KEYS = "1"
   .\sdt_inspection.exe
   ```
3. 启动时会在日志打印当前策略（INFO 行）

开启后，设备公钥需已在 Paramiko / 系统 known_hosts 中。若看到
`No matching host key found`，需先用自动接受模式连接一次以记录密钥。

## 输出与日志

- 结果日志：`InspectionLogs/<YYYY_MM_DD>/<设备>_<地址>_<时间戳>.txt`（密码已脱敏）
- 主界面实时显示每台设备状态：成功（绿）/ 失败（红）/ 已取消（灰）/ 进行中（蓝）

## 安全注意事项

- 设备密码来自配置文件，请限制 `config/` 目录权限，不要将含真实密码的配置提交到任何公开位置。
- `show run`、`display current-configuration` 等命令输出可能包含敏感配置，请妥善保管 `InspectionLogs`。
- 建议先使用测试设备验证驱动、提示符与分页行为。

## 版本与更新

版本记录见 [Releases](../../releases)。本仓库仅提供编译后的程序，不包含源代码。
