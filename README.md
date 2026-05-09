# Mac NAS Guardian

`Mac NAS Guardian` 是给旧款 Intel MacBook Pro 安装飞牛 OS 作为 NAS 使用时准备的宿主机硬件守护程序。

它的目标很明确：让同样把 MacBook 改成 NAS 的用户，可以在飞牛 OS 上更稳地控制温度、风扇和背光。

- 作者：xiaoker
- 博客：[www.xiaoker.com](https://www.xiaoker.com)

## 适用场景

当前项目主要面向这类环境：

- 旧款 Intel MacBook Pro
- 安装飞牛 OS，作为 NAS 长期开机使用
- 可以进入飞牛 OS 宿主机，并拥有 root 或 sudo 权限
- Linux 内核能暴露 `applesmc`、`coretemp`、`hwmon` 等硬件接口

它不是通用 NAS 风扇控制器。极空间、群晖、威联通、绿联等原厂 NAS 的硬件接口通常不同，不能保证直接可用。

## 主要功能

- 实时查看 CPU 温度、风扇转速、风扇接管状态
- 根据温度曲线自动设置风扇目标转速
- 提供静音、均衡、强冷三种预设
- 支持自定义低温、高温、危险温度和转速范围
- 支持键盘背光开机自动关闭
- 支持控制台自动熄屏，但不让系统休眠
- 自动探测温度、风扇、背光和 logo 背光能力
- 提供本地 Web 管理页面和 JSON API

## 硬件能力说明

### 风扇控制

风扇控制基于 Linux 下的 `applesmc` 和 `hwmon` 接口。程序会尝试读取：

```text
/sys/class/hwmon/*
/sys/devices/platform/applesmc.*
```

如果系统只允许读取风扇转速，不允许写入目标转速，页面会显示“仅监控”，不会伪装成已经接管风扇。

### 键盘背光

键盘背光优先使用：

```text
/sys/class/leds/smc::kbd_backlight/brightness
/sys/class/leds/smc::kbd_backlight/max_brightness
```

如果没有检测到可控背光设备，页面会自动禁用相关控制项。

### Apple Logo 背光

项目默认不提供独立 logo 开关。

原因是很多 MacBook 机型没有独立可编程的 Apple logo 背光接口；老款发光 logo 通常也和屏幕背光物理联动，无法通过软件单独关闭。

## 快速安装

先把项目放到飞牛 OS 宿主机上，例如：

```bash
scp -r mac-nas-guardian root@NAS-IP:/tmp/
```

进入 NAS 宿主机：

```bash
ssh root@NAS-IP
```

建议先跑硬件探测：

```bash
bash /tmp/mac-nas-guardian/scripts/probe-hardware.sh
```

确认能读到温度和风扇接口后安装：

```bash
sudo bash /tmp/mac-nas-guardian/scripts/install-host.sh
```

安装完成后访问：

```text
http://NAS-IP:18923/
```

## 更新程序

如果已经安装过，只更新主程序即可：

```bash
scp app/guardian_agent.py root@NAS-IP:/tmp/guardian_agent.py
ssh root@NAS-IP
sudo cp /tmp/guardian_agent.py /opt/mac-nas-guardian/app/guardian_agent.py
sudo chmod +x /opt/mac-nas-guardian/app/guardian_agent.py
sudo systemctl restart mac-nas-guardian.service
```

检查服务状态：

```bash
sudo systemctl status mac-nas-guardian.service
```

查看日志：

```bash
sudo journalctl -u mac-nas-guardian.service -f
```

## 默认风扇策略

默认策略偏保守，优先避免 NAS 长时间高温：

- `45C` 以下保持低转速
- `45C-65C` 逐渐提速
- `65C-80C` 快速抬升
- `80C` 及以上直接最大风扇

配置文件位置：

```text
/etc/mac-nas-guardian/config.json
```

关键字段：

```json
{
  "policy": {
    "low_temp": 45.0,
    "high_temp": 65.0,
    "danger_temp": 80.0,
    "min_rpm": 2200,
    "max_rpm": 6100,
    "poll_interval_sec": 2
  }
}
```

也可以直接在 Web 页面里修改这些配置。

## 服务路径

安装脚本会写入这些位置：

```text
/opt/mac-nas-guardian/app/guardian_agent.py
/etc/mac-nas-guardian/config.json
/etc/systemd/system/mac-nas-guardian.service
```

服务启动命令：

```text
/usr/bin/python3 /opt/mac-nas-guardian/app/guardian_agent.py --config /etc/mac-nas-guardian/config.json
```

## 项目结构

```text
app/guardian_agent.py             主程序，包含 agent、Web UI 和 API
config/guardian.example.json      默认 JSON 配置
config/guardian.example.yaml      YAML 配置样例
scripts/install-host.sh           宿主机安装脚本
scripts/probe-hardware.sh         硬件探测脚本
systemd/mac-nas-guardian.service  systemd 服务定义
docs/architecture.md              技术架构说明
docs/product-spec.md              产品设计说明
deploy/docker-compose.yml         容器部署草案
```

## API

状态接口：

```http
GET /api/v1/status
```

风扇策略：

```http
POST /api/v1/fan-policy
```

键盘背光：

```http
POST /api/v1/backlight/keyboard
```

控制台熄屏：

```http
POST /api/v1/console
```

## 安全与风险

这个程序需要 root 权限读写宿主机硬件接口。使用前请理解这些风险：

- 错误的风扇配置可能导致机器过热
- 不同 MacBook 子型号暴露的 sysfs 路径可能不同
- 飞牛 OS 或内核更新后，硬件接口可能变化
- 如果无法确认风扇写入接口，请先只观察状态，不要长期依赖自动控制

建议首次部署后观察一段时间温度、风扇转速和日志，再长期运行。

## 适配其他系统

从原理上，程序不依赖飞牛 OS 品牌本身，而是依赖 Linux 宿主机暴露的硬件接口。

如果同一台 MacBook 改装运行 Debian、Ubuntu、OpenMediaVault、CasaOS 等系统，并且 `applesmc/coretemp/hwmon` 接口可用，理论上可以适配。

如果是原厂 NAS 设备，例如极空间、群晖、威联通、绿联 NAS，通常需要重新实现硬件适配层。

## 贡献

欢迎同样使用旧 MacBook 改 NAS 的用户提交：

- 硬件探测结果
- 不同 MacBook 型号的风扇路径
- 飞牛 OS 版本兼容性反馈
- 安装脚本改进
- Web 管理页面体验改进

提交 issue 时建议包含：

```bash
bash scripts/probe-hardware.sh
sudo systemctl status mac-nas-guardian.service
sudo journalctl -u mac-nas-guardian.service -n 100
```

注意不要提交真实内网密码、密钥、令牌或个人隐私信息。
