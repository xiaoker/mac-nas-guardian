# 技术架构

## 1. 总体结构

```text
飞牛 OS Web UI
        |
        v
guardian-web API
        |
        v
guardian-agent
        |
        +-- /sys/devices/platform/applesmc.*
        +-- /sys/class/leds/smc::kbd_backlight
        +-- /sys/class/hwmon/*
        +-- journald / local log
```

## 2. 组件职责

### guardian-agent

职责：

- 周期性读取温度与风扇状态
- 应用风扇控制策略
- 控制键盘背光
- 输出健康状态
- 暴露本地 HTTP API 给前端

建议实现语言：

- Go

理由：

- 单二进制，部署简单
- 对 sysfs 读写足够直接
- 做守护进程和 HTTP API 都合适

### guardian-web

职责：

- 展示状态
- 修改配置
- 展示宿主机能力探测结果
- 呈现日志和告警

建议实现：

- 静态前端 + 反向代理到 agent API
- 或直接由 agent 内嵌静态页面，减少组件数

MVP 建议：

- 直接由 `guardian-agent` 内嵌前端静态资源
- 不单独拆 `guardian-web`

## 3. 宿主机接口

### 温度

优先读取：

- `/sys/class/hwmon/*/temp*_input`

并结合名称过滤：

- `coretemp`

### 风扇

常见接口形态：

- `/sys/devices/platform/applesmc.*/fan*_input`
- `/sys/devices/platform/applesmc.*/fan*_min`
- `/sys/devices/platform/applesmc.*/fan*_max`

说明：

- 标准 hwmon 文档定义了 `fan*_input`、`fan*_min`、`fan*_max`、`fan*_target` 这类语义
- Apple 机器上实际暴露路径会因内核版本不同而变化，应用必须做动态探测，不能写死具体数字编号

### 键盘背光

优先读取：

- `/sys/class/leds/smc::kbd_backlight/brightness`
- `/sys/class/leds/smc::kbd_backlight/max_brightness`

### Logo 背光

策略：

- 不假设存在独立 sysfs 设备
- 若未探测到独立接口，直接标记为 `unsupported`
- 不提供“伪开关”

这是一个刻意的产品约束，避免让用户误以为一定能关闭后盖 logo。

## 4. API 草案

### `GET /api/v1/status`

返回：

```json
{
  "cpu_temp_c": 48.5,
  "fan_rpm": [3200, 3180],
  "profile": "balanced",
  "keyboard_backlight": {
    "supported": true,
    "brightness": 0,
    "max": 255
  },
  "logo_backlight": {
    "supported": false,
    "reason": "no-independent-device"
  }
}
```

### `POST /api/v1/profile`

请求：

```json
{
  "profile": "cooling"
}
```

### `POST /api/v1/fan-policy`

请求：

```json
{
  "low_temp": 38,
  "high_temp": 50,
  "danger_temp": 72,
  "min_rpm": 2200,
  "max_rpm": 6100,
  "poll_interval_sec": 2
}
```

### `POST /api/v1/backlight/keyboard`

请求：

```json
{
  "enabled": false,
  "brightness": 0
}
```

## 5. 风扇策略

采用分段线性策略：

- `temp <= low_temp`：维持 `min_rpm`
- `low_temp < temp < high_temp`：线性抬升
- `high_temp <= temp < danger_temp`：快速逼近 `max_rpm`
- `temp >= danger_temp`：直接 `max_rpm`

保护规则：

- 任意传感器失效时切为保守模式
- 连续 3 次写入失败则停止接管，并上报告警
- 用户可一键恢复系统默认

## 6. 权限与部署

如果以容器运行，需要：

- `privileged: true` 或精细化设备与挂载授权
- 挂载 `/sys:/sys`
- 挂载 `/run:/run` 用于系统通信
- `network_mode: host` 便于本地服务暴露

更稳妥的生产方案：

- `guardian-agent` 安装在宿主机 systemd
- 飞牛 OS 只提供前端管理页面

## 7. 风险点

- 飞牛 OS 的宿主系统是否允许加载 `applesmc`
- 容器内对 sysfs 的写权限是否被平台限制
- 不同 MacBook Pro 子型号的风扇路径可能不一致
- “logo 常亮”可能是用户把键盘背光或屏幕漏光误认为 logo，首次部署必须做机型核验
