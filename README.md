# Mac NAS Guardian

`Mac NAS Guardian` 是给 2014 款 Intel MacBook Pro 运行飞牛 OS 作为 NAS 场景设计的宿主机硬件控制应用。

作者：xiaoker

博客：[www.xiaoker.com](https://www.xiaoker.com)

许可证：非商业用途可使用，商业用途需单独授权。详见 [`LICENSE`](/Users/xiaoker/ke/mac-nas-guardian/LICENSE)。

目标：

- 根据 CPU 温度自动调节风扇，避免长时间高温降频或过热
- 提供背光控制能力，优先支持键盘背光
- 判断“Apple logo 常亮”是否具备软件可控条件，并在不可控时给出替代方案
- 通过飞牛 OS 中的 Web 界面完成配置、状态查看和告警

## 当前实现

这个目录现在已经包含一个可运行的最小版本：

- [`app/guardian_agent.py`](/Users/xiaoker/ke/mac-nas-guardian/app/guardian_agent.py)
  - Python 3 标准库实现
  - 读取 CPU 温度
  - 读取风扇转速
  - 尝试写入 `fan*_target`
  - 提供本地 Web 管理页和 JSON API
  - 支持控制台自动熄屏但系统不休眠
- [`config/guardian.example.json`](/Users/xiaoker/ke/mac-nas-guardian/config/guardian.example.json)
  - 默认把 `danger_temp` 设为 `80.0`
- [`systemd/mac-nas-guardian.service`](/Users/xiaoker/ke/mac-nas-guardian/systemd/mac-nas-guardian.service)
  - 宿主机服务定义
- [`scripts/install-host.sh`](/Users/xiaoker/ke/mac-nas-guardian/scripts/install-host.sh)
  - 宿主机安装脚本

## 结论先行

- 风扇自动控制：可做，基于 Linux 的 `applesmc` + `coretemp` 接口实现
- 键盘背光控制：通常可做，Linux 下常见路径为 `/sys/class/leds/smc::kbd_backlight/brightness`
- 后盖 Apple logo 独立开关：大概率不可做
  - 如果你的机器是 Retina 机型，通常没有独立发光 logo
  - 如果是老款带发光 logo 的机型，该灯通常与屏幕背光物理联动，不是独立可编程设备

因此本应用建议命名为：

- 中文：`飞牛 Mac 守护`
- 英文：`Mac NAS Guardian`

## 推荐部署形态

不是单纯的前端应用，而是两部分：

1. `guardian-agent`
   - 运行在飞牛 OS 宿主机
   - 负责读写 `/sys`、加载内核模块、执行风扇策略
2. `guardian-web`
   - 运行在飞牛 OS 应用容器
   - 负责配置页面、状态展示、日志和告警

这样做的原因很直接：风扇和背光控制需要宿主机权限，单纯容器化页面无法稳定控制硬件。

## 功能模块

### 1. 风扇自动控制

- 读取 CPU 温度
- 读取当前风扇转速
- 根据温度曲线自动设置目标转速
- 支持静音、均衡、强冷三种预设
- 支持用户自定义温度阈值
- 支持“故障回退”
  - 读不到温度时切回系统默认
  - 温度超过危险值时直接打满风扇

### 2. 背光控制

- 键盘背光开关
- 键盘背光亮度调节
- 定时熄灭
- NAS 模式开机自动关闭

### 3. 设备能力探测

启动时自动检测：

- 是否存在 `applesmc`
- 是否存在 `coretemp`
- 是否存在 `smc::kbd_backlight`
- 是否存在可写风扇目标接口
- 当前机型是否可能具备独立 logo 背光

如果检测结果表明 logo 不可独立控制，界面中不显示该开关，只显示说明。

## 安装方法

前提：

- 飞牛 OS 宿主机里有 `python3`
- 宿主机是 root 或有 sudo
- 内核已经暴露温度与风扇 sysfs 接口

建议先跑硬件探测：

```bash
bash /path/to/mac-nas-guardian/scripts/probe-hardware.sh
```

如果确认有这些接口，再安装：

```bash
sudo bash /path/to/mac-nas-guardian/scripts/install-host.sh
```

安装完成后访问：

```bash
http://NAS-IP:18923/
```

如果你后面更新了程序，例如我补了“键盘背光可配置”这类新功能，需要重新拷贝项目并重启服务：

```bash
sudo cp /tmp/mac-nas-guardian/app/guardian_agent.py /opt/mac-nas-guardian/app/guardian_agent.py
sudo systemctl restart mac-nas-guardian.service
```

## 80 度自动风扇

默认配置已经是这个策略：

- `45C` 以下保持低转速
- `45C-65C` 逐渐提速
- `65C-80C` 快速抬升
- `80C` 及以上直接最大风扇

如果你要改，编辑：

- [`config/guardian.example.json`](/Users/xiaoker/ke/mac-nas-guardian/config/guardian.example.json)
- 实际安装后则改 `/etc/mac-nas-guardian/config.json`

关键字段：

```json
{
  "policy": {
    "low_temp": 45.0,
    "high_temp": 65.0,
    "danger_temp": 80.0,
    "min_rpm": 2200,
    "max_rpm": 6100
  }
}
```

## 目录说明

- [`docs/product-spec.md`](/Users/xiaoker/ke/mac-nas-guardian/docs/product-spec.md)：产品设计与交互方案
- [`docs/architecture.md`](/Users/xiaoker/ke/mac-nas-guardian/docs/architecture.md)：技术架构与接口设计
- [`deploy/docker-compose.yml`](/Users/xiaoker/ke/mac-nas-guardian/deploy/docker-compose.yml)：飞牛 OS 容器部署草案
- [`config/guardian.example.yaml`](/Users/xiaoker/ke/mac-nas-guardian/config/guardian.example.yaml)：策略配置样例
- [`config/guardian.example.json`](/Users/xiaoker/ke/mac-nas-guardian/config/guardian.example.json)：当前程序实际使用的配置样例
- [`systemd/mac-nas-guardian.service`](/Users/xiaoker/ke/mac-nas-guardian/systemd/mac-nas-guardian.service)：宿主机服务
- [`scripts/install-host.sh`](/Users/xiaoker/ke/mac-nas-guardian/scripts/install-host.sh)：安装脚本

## 开源发布建议

如果你准备发布到 GitHub，当前目录已经基本够用。建议发布前再做两件事：

1. 确认当前这份社区许可证是否符合你的商业授权预期
2. 确认不要把 NAS 上的真实配置、缓存和临时文件提交进去

项目里已经补了 `.gitignore`，会忽略常见缓存和 `tmp/` 目录。

## 下一步

后续如果你要继续，我建议做两件事：

1. 在你的飞牛 OS 机器上跑探测脚本，确认真实风扇写入路径
2. 如果 `fan*_target` 不可写，再针对那台机器补专用写入适配
