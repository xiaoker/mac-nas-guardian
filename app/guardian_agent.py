#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import glob
import json
import logging
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_CONFIG: Dict[str, Any] = {
    "server": {
        "listen_host": "0.0.0.0",
        "listen_port": 18923,
    },
    "hardware": {
        "temp_name_allowlist": ["coretemp"],
        "temp_input_globs": ["/sys/class/hwmon/*/temp*_input"],
        "fan_input_globs": ["/sys/devices/platform/applesmc.*/fan*_input"],
        "fan_min_globs": ["/sys/devices/platform/applesmc.*/fan*_min"],
        "fan_max_globs": ["/sys/devices/platform/applesmc.*/fan*_max"],
        "fan_target_globs": ["/sys/devices/platform/applesmc.*/fan*_target"],
        "fan_manual_globs": ["/sys/devices/platform/applesmc.*/fan*_manual"],
        "fan_output_globs": ["/sys/devices/platform/applesmc.*/fan*_output"],
        "keyboard_backlight_path": "/sys/class/leds/smc::kbd_backlight/brightness",
        "keyboard_backlight_max_path": "/sys/class/leds/smc::kbd_backlight/max_brightness",
    },
    "policy": {
        "enabled": True,
        "profile": "balanced",
        "low_temp": 45.0,
        "high_temp": 65.0,
        "danger_temp": 80.0,
        "min_rpm": 2000,
        "max_rpm": 6200,
        "poll_interval_sec": 2,
        "sensor_fail_max": 3,
    },
    "backlight": {
        "disable_on_boot": True,
        "boot_brightness": 0,
        "idle_off_minutes": 5,
    },
    "console": {
        "blank_enabled": True,
        "blank_minutes": 1,
        "tty_path": "/dev/tty0",
    },
    "ui": {
        "title": "Mac NAS Guardian",
    },
}


INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Mac NAS Guardian</title>
  <style>
    :root {
      --bg: #f3efe6;
      --panel: rgba(255,255,255,0.78);
      --line: rgba(30, 41, 59, 0.16);
      --text: #1d2433;
      --muted: #536072;
      --accent: #c75b12;
      --ok: #2d7d46;
      --warn: #b56800;
      --danger: #b42318;
      --shadow: 0 18px 50px rgba(40, 36, 31, 0.14);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--text);
      font-family: "Avenir Next", "PingFang SC", "Hiragino Sans GB", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(223, 141, 34, 0.28), transparent 28%),
        radial-gradient(circle at top right, rgba(55, 116, 167, 0.18), transparent 26%),
        linear-gradient(180deg, #f5f1e9 0%, #ece4d6 100%);
      min-height: 100vh;
    }
    .shell {
      max-width: 1100px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }
    .hero {
      display: grid;
      gap: 16px;
      margin-bottom: 18px;
    }
    .hero-card {
      background: linear-gradient(135deg, rgba(29, 36, 51, 0.92), rgba(69, 47, 18, 0.9));
      color: #f8f4eb;
      border-radius: 28px;
      padding: 24px;
      box-shadow: 0 24px 60px rgba(30, 23, 18, 0.22);
      position: relative;
      overflow: hidden;
    }
    .hero-card::after {
      content: "";
      position: absolute;
      inset: auto -40px -40px auto;
      width: 180px;
      height: 180px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(255,255,255,0.22), transparent 68%);
      pointer-events: none;
    }
    .hero-top {
      display: grid;
      gap: 10px;
    }
    .eyebrow {
      color: #f6c788;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      font-size: 12px;
    }
    h1 {
      margin: 0;
      font-size: clamp(28px, 4vw, 46px);
      line-height: 1.05;
    }
    .subtitle {
      margin: 0;
      color: rgba(248, 244, 235, 0.78);
      max-width: 760px;
      line-height: 1.6;
    }
    .hero-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 6px;
    }
    .meta-inline {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 0;
      border-radius: 0;
      background: transparent;
      border: 0;
    }
    .meta-label {
      font-size: 12px;
      color: rgba(248, 244, 235, 0.62);
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    .meta-value {
      font-size: 14px;
      font-weight: 700;
      line-height: 1.4;
      word-break: break-word;
    }
    .meta-value a {
      color: #fff3dd;
      text-decoration: none;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 16px;
    }
    .card-primary {
      background: linear-gradient(180deg, rgba(255,255,255,0.92), rgba(255,247,236,0.9));
    }
    .grid-2 {
      display: grid;
      grid-template-columns: minmax(0, 1.3fr) minmax(280px, 0.7fr);
      gap: 16px;
      margin-top: 16px;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 22px;
      box-shadow: var(--shadow);
      padding: 20px;
      backdrop-filter: blur(12px);
    }
    .label {
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 8px;
    }
    .value {
      font-size: 36px;
      font-weight: 700;
      line-height: 1;
      font-variant-numeric: tabular-nums;
    }
    .status {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border-radius: 999px;
      padding: 6px 12px;
      font-size: 13px;
      font-weight: 600;
      margin-top: 12px;
      background: rgba(255,255,255,0.72);
    }
    .status.ok { color: var(--ok); }
    .status.warn { color: var(--warn); }
    .status.danger { color: var(--danger); }
    .two-col {
      display: grid;
      grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
      gap: 16px;
      margin-top: 16px;
    }
    .section-title {
      margin: 0 0 14px;
      font-size: 20px;
    }
    .section-subtitle {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.6;
      margin: -6px 0 14px;
    }
    .section-block {
      margin-top: 18px;
      padding-top: 18px;
      border-top: 1px solid rgba(30, 41, 59, 0.08);
    }
    .section-block:first-of-type {
      margin-top: 0;
      padding-top: 0;
      border-top: 0;
    }
    .muted {
      color: var(--muted);
      line-height: 1.55;
    }
    .form-grid {
      display: grid;
      gap: 12px;
    }
    label {
      display: grid;
      gap: 6px;
      font-size: 14px;
      font-weight: 600;
    }
    input, select, button {
      font: inherit;
    }
    input, select {
      width: 100%;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.88);
      padding: 12px 14px;
      color: var(--text);
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 14px;
    }
    .button-group {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }
    button {
      border: 0;
      border-radius: 999px;
      padding: 12px 18px;
      background: var(--accent);
      color: white;
      cursor: pointer;
      font-weight: 700;
    }
    button.secondary {
      background: #314158;
    }
    button.ghost {
      background: rgba(49, 65, 88, 0.08);
      color: var(--text);
      border: 1px solid rgba(30, 41, 59, 0.12);
    }
    .mono {
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 13px;
      white-space: pre-wrap;
      background: rgba(29, 36, 51, 0.06);
      border-radius: 16px;
      padding: 14px;
      line-height: 1.5;
    }
    .row {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      padding: 10px 0;
      border-bottom: 1px solid rgba(30, 41, 59, 0.08);
    }
    .row:last-child { border-bottom: 0; }
    .summary-grid {
      display: grid;
      gap: 12px;
    }
    .summary-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      padding: 12px 14px;
      border-radius: 16px;
      background: rgba(255,255,255,0.6);
      border: 1px solid rgba(30, 41, 59, 0.08);
    }
    .summary-label {
      color: var(--muted);
      font-size: 13px;
    }
    .summary-value {
      font-weight: 700;
      font-size: 14px;
    }
    .panel-grid {
      display: grid;
      grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr);
      gap: 16px;
      margin-top: 16px;
    }
    .stacked-sections {
      display: grid;
      gap: 18px;
    }
    .hint {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.6;
      margin-top: 8px;
    }
    details {
      margin-top: 16px;
    }
    summary {
      cursor: pointer;
      font-weight: 700;
      color: var(--text);
    }
    .footer {
      margin-top: 14px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.6;
      text-align: left;
    }
    .footer a {
      color: var(--accent);
      text-decoration: none;
      font-weight: 700;
    }
    @media (max-width: 860px) {
      .grid { grid-template-columns: 1fr; }
      .two-col { grid-template-columns: 1fr; }
      .grid-2 { grid-template-columns: 1fr; }
      .panel-grid { grid-template-columns: 1fr; }
      .shell { padding: 20px 14px 36px; }
      .footer { text-align: left; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <div class="hero">
      <div class="hero-card">
        <div class="hero-top">
          <div class="eyebrow">Mac NAS Guardian</div>
          <h1>MacBook NAS 守护中心</h1>
          <p class="subtitle">统一管理风扇策略、键盘背光和控制台熄屏。页面先回答“机器现在稳不稳”，再给你高频操作和详细配置。</p>
        </div>
        <div class="hero-meta">
          <div class="meta-inline"><span class="meta-label">作者</span><span class="meta-value">xiaoker</span></div>
          <div class="meta-inline"><span class="meta-label">博客</span><span class="meta-value"><a href="https://www.xiaoker.com" target="_blank" rel="noreferrer">www.xiaoker.com</a></span></div>
          <div class="meta-inline"><span class="meta-label">GitHub</span><span class="meta-value"><a href="https://github.com/xiaoker/mac-nas-guardian" target="_blank" rel="noreferrer">mac-nas-guardian</a></span></div>
          <div class="meta-inline"><span class="meta-label">当前入口</span><span class="meta-value">192.168.3.166:6688</span></div>
        </div>
      </div>
    </div>

    <div class="grid">
      <div class="card card-primary">
        <div class="label">CPU 最高温度</div>
        <div class="value" id="tempValue">--</div>
        <div class="status" id="tempStatus">等待数据</div>
      </div>
      <div class="card">
        <div class="label">当前风扇转速</div>
        <div class="value" id="fanValue">--</div>
        <div class="status" id="fanStatus">等待数据</div>
      </div>
      <div class="card">
        <div class="label">控制状态</div>
        <div class="value" id="policyValue">--</div>
        <div class="status" id="supportStatus">探测中</div>
      </div>
      <div class="card">
        <div class="label">熄屏状态</div>
        <div class="value" id="screenValue">--</div>
        <div class="status" id="screenStatus">等待数据</div>
      </div>
    </div>

    <div class="grid-2">
      <div class="card">
        <h2 class="section-title">守护总览</h2>
        <p class="section-subtitle">这里先看当前机器的守护状态，再决定是否需要去下面调整配置。</p>
        <div class="summary-grid" id="summaryGrid"></div>
      </div>

      <div class="card">
        <h2 class="section-title">快捷操作</h2>
        <p class="section-subtitle">高频动作不需要翻到底部，直接在这里执行。</p>
        <div class="button-group">
          <button type="button" id="refreshBtn">刷新状态</button>
          <button type="button" class="secondary" id="backlightOffBtn">立即关闭背光</button>
          <button type="button" class="ghost" id="coolingPresetBtn">切换到强冷</button>
          <button type="button" class="ghost" id="balancedPresetBtn">恢复均衡</button>
        </div>
        <p class="hint">风扇模式切换会直接覆盖当前风扇阈值配置。网页所有配置保存后立即生效。</p>
      </div>
    </div>

    <div class="panel-grid">
      <div class="card">
        <h2 class="section-title">风扇策略</h2>
        <p class="section-subtitle">建议把危险温度设成 80C，而不是等到 80C 才开始转。这样能避免 NAS 长时间高负载时先顶到高温。</p>
        <div class="button-group" style="margin-bottom:14px;">
          <button type="button" class="ghost preset-btn" data-profile="quiet" data-low="40" data-high="55" data-danger="75" data-min="1800" data-max="5000">静音</button>
          <button type="button" class="ghost preset-btn" data-profile="balanced" data-low="45" data-high="65" data-danger="80" data-min="2200" data-max="6100">均衡</button>
          <button type="button" class="ghost preset-btn" data-profile="cooling" data-low="40" data-high="55" data-danger="80" data-min="2600" data-max="6100">强冷</button>
        </div>
        <form id="policyForm" class="form-grid">
          <label>模式
            <select name="profile">
              <option value="balanced">均衡</option>
              <option value="cooling">强冷</option>
              <option value="quiet">静音</option>
              <option value="custom">自定义</option>
            </select>
          </label>
          <label>低温阈值 low_temp
            <input type="number" step="0.1" name="low_temp">
          </label>
          <label>高温阈值 high_temp
            <input type="number" step="0.1" name="high_temp">
          </label>
          <label>危险温度 danger_temp
            <input type="number" step="0.1" name="danger_temp">
          </label>
          <label>最小转速 min_rpm
            <input type="number" name="min_rpm">
          </label>
          <label>最大转速 max_rpm
            <input type="number" name="max_rpm">
          </label>
          <label>轮询间隔 poll_interval_sec
            <input type="number" name="poll_interval_sec">
          </label>
          <div class="actions">
            <button type="submit">保存策略</button>
          </div>
        </form>
      </div>

      <div class="card">
        <div class="stacked-sections">
          <div>
            <h2 class="section-title">键盘背光</h2>
            <p class="section-subtitle">适合 NAS 常亮场景。开机可自动关闭，必要时也能保留亮度。</p>
            <form id="backlightForm" class="form-grid">
              <label>开机默认行为
                <select name="disable_on_boot">
                  <option value="true">开机关闭</option>
                  <option value="false">开机保留亮度</option>
                </select>
              </label>
              <label>默认亮度
                <input type="number" name="brightness" min="0" step="1">
              </label>
              <div class="actions">
                <button type="submit">保存背光</button>
              </div>
            </form>
          </div>
          <div class="section-block">
            <h2 class="section-title">控制台熄屏</h2>
            <p class="section-subtitle">屏幕熄灭但系统不休眠，按键可恢复显示。你之前已经在实机上验证过这个方案可用。</p>
            <form id="consoleForm" class="form-grid">
              <label>开机自动熄屏
                <select name="blank_enabled">
                  <option value="true">启用</option>
                  <option value="false">关闭</option>
                </select>
              </label>
              <label>空闲几分钟后熄屏
                <input type="number" name="blank_minutes" min="0" step="1">
              </label>
              <div class="actions">
                <button type="submit">保存熄屏</button>
              </div>
            </form>
          </div>
        </div>
      </div>

      <div class="card">
        <h2 class="section-title">宿主机能力</h2>
        <p class="section-subtitle">这里展示当前机器探测到的硬件能力，用来判断哪些控制项真实可用。</p>
        <div id="capabilities"></div>
        <details>
          <summary>高级调试信息</summary>
          <div class="mono" id="snapshot" style="margin-top:12px;">等待数据</div>
        </details>
      </div>
    </div>
    <div class="footer">
      项目主页：<a href="https://github.com/xiaoker/mac-nas-guardian" target="_blank" rel="noreferrer">github.com/xiaoker/mac-nas-guardian</a>
    </div>
  </div>

  <script>
    async function readStatus() {
      const response = await fetch('/api/v1/status');
      if (!response.ok) {
        throw new Error('status request failed');
      }
      return response.json();
    }

    function tempClass(temp, danger) {
      if (temp >= danger) return ['danger', '危险'];
      if (temp >= danger - 8) return ['warn', '偏高'];
      return ['ok', '正常'];
    }

    function fanText(rpms) {
      if (!rpms || !rpms.length) return '--';
      return rpms.join(' / ') + ' RPM';
    }

    function renderCapabilities(status) {
      const items = [
        ['温度传感器', status.capabilities.temperature_supported ? '可用' : '不可用'],
        ['风扇读取', status.capabilities.fan_supported ? '可用' : '不可用'],
        ['风扇写入', status.capabilities.fan_control_supported ? '可用' : '不可用'],
        ['键盘背光', status.capabilities.keyboard_backlight_supported ? '可用' : '不可用'],
        ['Logo 单独控制', status.capabilities.logo_backlight_supported ? '可用' : '不可用']
      ];
      const root = document.getElementById('capabilities');
      root.innerHTML = items.map(([k, v]) => '<div class="row"><div>' + k + '</div><strong>' + v + '</strong></div>').join('');
    }

    function renderSummary(status) {
      const items = [
        ['风扇控制', status.capabilities.fan_control_supported ? '已接管' : '仅监控'],
        ['键盘背光', status.keyboard_backlight.brightness === 0 ? '已关闭' : ('亮度 ' + status.keyboard_backlight.brightness)],
        ['控制台熄屏', status.console_config.blank_enabled ? ('已启用 / ' + status.console_config.blank_minutes + ' 分钟') : '已关闭'],
        ['Logo 独立控制', status.logo_backlight.supported ? '可用' : '不支持'],
        ['最近错误', status.last_error || '运行正常']
      ];
      const root = document.getElementById('summaryGrid');
      root.innerHTML = items.map(([k, v]) => '<div class="summary-item"><div class="summary-label">' + k + '</div><div class="summary-value">' + v + '</div></div>').join('');
    }

    function fillForm(policy) {
      const form = document.getElementById('policyForm');
      for (const [key, value] of Object.entries(policy)) {
        const field = form.elements.namedItem(key);
        if (!field) continue;
        field.value = value;
      }
    }

    function fillBacklightForm(status) {
      const form = document.getElementById('backlightForm');
      form.disable_on_boot.value = String(status.backlight_config.disable_on_boot);
      form.brightness.max = status.keyboard_backlight.max || 255;
      form.brightness.value = status.backlight_config.disable_on_boot ? 0 : (status.backlight_config.boot_brightness || status.keyboard_backlight.brightness || 0);
    }

    function fillConsoleForm(status) {
      const form = document.getElementById('consoleForm');
      form.blank_enabled.value = String(status.console_config.blank_enabled);
      form.blank_minutes.value = status.console_config.blank_minutes;
    }

    function renderStatus(status) {
      const temp = status.cpu_temp_c;
      const [levelClass, levelText] = tempClass(temp || 0, status.policy.danger_temp);
      document.getElementById('tempValue').textContent = temp == null ? '--' : temp.toFixed(1) + 'C';
      const tempStatus = document.getElementById('tempStatus');
      tempStatus.textContent = levelText;
      tempStatus.className = 'status ' + levelClass;

      document.getElementById('fanValue').textContent = fanText(status.fan_rpm);
      const fanStatus = document.getElementById('fanStatus');
      fanStatus.textContent = status.last_applied_rpm ? ('目标 ' + status.last_applied_rpm + ' RPM') : '暂无目标值';
      fanStatus.className = 'status ' + (status.capabilities.fan_control_supported ? 'ok' : 'warn');

      document.getElementById('policyValue').textContent = status.policy.profile;
      const supportStatus = document.getElementById('supportStatus');
      supportStatus.textContent = status.capabilities.fan_control_supported ? '已接管风扇' : '仅监控';
      supportStatus.className = 'status ' + (status.capabilities.fan_control_supported ? 'ok' : 'warn');

      document.getElementById('screenValue').textContent = status.console_config.blank_enabled ? '已启用' : '已关闭';
      const screenStatus = document.getElementById('screenStatus');
      screenStatus.textContent = status.console_config.blank_enabled ? (status.console_config.blank_minutes + ' 分钟后熄屏') : '不自动熄屏';
      screenStatus.className = 'status ' + (status.console_blank_applied ? 'ok' : 'warn');

      document.getElementById('snapshot').textContent = JSON.stringify(status, null, 2);
      renderSummary(status);
      renderCapabilities(status);
      fillForm(status.policy);
      fillBacklightForm(status);
      fillConsoleForm(status);
    }

    async function refreshStatus() {
      try {
        const status = await readStatus();
        renderStatus(status);
      } catch (error) {
        document.getElementById('snapshot').textContent = '读取失败：' + error.message;
      }
    }

    document.getElementById('policyForm').addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = event.target;
      const payload = {
        profile: form.profile.value,
        low_temp: Number(form.low_temp.value),
        high_temp: Number(form.high_temp.value),
        danger_temp: Number(form.danger_temp.value),
        min_rpm: Number(form.min_rpm.value),
        max_rpm: Number(form.max_rpm.value),
        poll_interval_sec: Number(form.poll_interval_sec.value)
      };
      const response = await fetch('/api/v1/fan-policy', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      if (!response.ok) {
        const text = await response.text();
        alert(text);
        return;
      }
      await refreshStatus();
    });

    document.getElementById('backlightForm').addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = event.target;
      const payload = {
        enabled: form.disable_on_boot.value !== 'true',
        disable_on_boot: form.disable_on_boot.value === 'true',
        brightness: Number(form.brightness.value)
      };
      const response = await fetch('/api/v1/backlight/keyboard', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      if (!response.ok) {
        const text = await response.text();
        alert(text);
        return;
      }
      await refreshStatus();
    });

    document.getElementById('backlightOffBtn').addEventListener('click', async () => {
      const response = await fetch('/api/v1/backlight/keyboard', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({enabled: false, disable_on_boot: true, brightness: 0})
      });
      if (!response.ok) {
        const text = await response.text();
        alert(text);
        return;
      }
      await refreshStatus();
    });

    document.getElementById('consoleForm').addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = event.target;
      const payload = {
        blank_enabled: form.blank_enabled.value === 'true',
        blank_minutes: Number(form.blank_minutes.value)
      };
      const response = await fetch('/api/v1/console', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      if (!response.ok) {
        const text = await response.text();
        alert(text);
        return;
      }
      await refreshStatus();
    });

    async function savePolicy(payload) {
      const response = await fetch('/api/v1/fan-policy', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      if (!response.ok) {
        const text = await response.text();
        alert(text);
        return;
      }
      await refreshStatus();
    }

    document.querySelectorAll('.preset-btn').forEach((button) => {
      button.addEventListener('click', () => {
        const form = document.getElementById('policyForm');
        form.profile.value = button.dataset.profile;
        form.low_temp.value = button.dataset.low;
        form.high_temp.value = button.dataset.high;
        form.danger_temp.value = button.dataset.danger;
        form.min_rpm.value = button.dataset.min;
        form.max_rpm.value = button.dataset.max;
      });
    });

    document.getElementById('coolingPresetBtn').addEventListener('click', async () => {
      await savePolicy({
        profile: 'cooling',
        low_temp: 40,
        high_temp: 55,
        danger_temp: 80,
        min_rpm: 2600,
        max_rpm: 6100,
        poll_interval_sec: Number(document.getElementById('policyForm').poll_interval_sec.value || 2)
      });
    });

    document.getElementById('balancedPresetBtn').addEventListener('click', async () => {
      await savePolicy({
        profile: 'balanced',
        low_temp: 45,
        high_temp: 65,
        danger_temp: 80,
        min_rpm: 2200,
        max_rpm: 6100,
        poll_interval_sec: Number(document.getElementById('policyForm').poll_interval_sec.value || 2)
      });
    });

    document.getElementById('refreshBtn').addEventListener('click', refreshStatus);
    refreshStatus();
    setInterval(refreshStatus, 4000);
  </script>
</body>
</html>
"""


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def read_json_file(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def read_int(path: Path) -> int:
    return int(read_text(path))


def write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class FanDevice:
    index: int
    input_path: Path
    min_path: Optional[Path]
    max_path: Optional[Path]
    target_path: Optional[Path]
    manual_path: Optional[Path]
    output_path: Optional[Path]

    def current_rpm(self) -> Optional[int]:
        if not self.input_path.exists():
            return None
        try:
            return read_int(self.input_path)
        except (OSError, ValueError):
            return None

    def min_rpm(self) -> Optional[int]:
        if not self.min_path or not self.min_path.exists():
            return None
        try:
            return read_int(self.min_path)
        except (OSError, ValueError):
            return None

    def max_rpm(self) -> Optional[int]:
        if not self.max_path or not self.max_path.exists():
            return None
        try:
            return read_int(self.max_path)
        except (OSError, ValueError):
            return None

    def writable(self) -> bool:
        if self.target_path and os.access(self.target_path, os.W_OK):
            return True
        return bool(
            self.manual_path
            and self.output_path
            and os.access(self.manual_path, os.W_OK)
            and os.access(self.output_path, os.W_OK)
        )

    def set_target(self, rpm: int) -> None:
        if self.target_path:
            write_text(self.target_path, f"{rpm}\n")
            return
        if self.manual_path and self.output_path:
            write_text(self.manual_path, "1\n")
            write_text(self.output_path, f"{rpm}\n")
            return
        raise RuntimeError("fan target path unavailable")

    def disable_manual(self) -> None:
        if self.manual_path and os.access(self.manual_path, os.W_OK):
            write_text(self.manual_path, "0\n")


class HardwareManager:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self._fan_devices = self._discover_fans()
        self._temp_paths = self._discover_temp_paths()
        self._keyboard_backlight = self._discover_keyboard_backlight()

    def refresh(self) -> None:
        self._fan_devices = self._discover_fans()
        self._temp_paths = self._discover_temp_paths()
        self._keyboard_backlight = self._discover_keyboard_backlight()

    def capabilities(self) -> Dict[str, bool]:
        return {
            "temperature_supported": bool(self._temp_paths),
            "fan_supported": bool(self._fan_devices),
            "fan_control_supported": any(device.writable() for device in self._fan_devices),
            "keyboard_backlight_supported": self._keyboard_backlight is not None,
            "logo_backlight_supported": False,
        }

    def keyboard_backlight_status(self) -> Dict[str, Any]:
        if not self._keyboard_backlight:
            return {"supported": False, "brightness": None, "max": None}
        brightness_path, max_path = self._keyboard_backlight
        try:
            return {
                "supported": True,
                "brightness": read_int(brightness_path),
                "max": read_int(max_path),
            }
        except (OSError, ValueError):
            return {"supported": True, "brightness": None, "max": None}

    def set_keyboard_backlight(self, brightness: int) -> int:
        if not self._keyboard_backlight:
            raise RuntimeError("keyboard backlight unavailable")
        brightness_path, max_path = self._keyboard_backlight
        maximum = read_int(max_path)
        value = int(clamp(brightness, 0, maximum))
        write_text(brightness_path, f"{value}\n")
        return value

    def disable_keyboard_backlight(self) -> None:
        if not self._keyboard_backlight:
            return
        self.set_keyboard_backlight(0)

    def read_cpu_temp_c(self) -> Optional[float]:
        temps: List[float] = []
        for path in self._temp_paths:
            try:
                raw = read_int(path)
            except (OSError, ValueError):
                continue
            if raw > 1000:
                temps.append(raw / 1000.0)
            else:
                temps.append(float(raw))
        if not temps:
            return None
        return max(temps)

    def read_fan_rpms(self) -> List[int]:
        rpms: List[int] = []
        for device in self._fan_devices:
            rpm = device.current_rpm()
            if rpm is not None:
                rpms.append(rpm)
        return rpms

    def computed_bounds(self) -> Dict[str, Optional[int]]:
        mins = [rpm for rpm in (device.min_rpm() for device in self._fan_devices) if rpm is not None]
        maxs = [rpm for rpm in (device.max_rpm() for device in self._fan_devices) if rpm is not None]
        return {
            "fan_min": min(mins) if mins else None,
            "fan_max": max(maxs) if maxs else None,
        }

    def set_all_fan_targets(self, rpm: int) -> int:
        applied = 0
        for device in self._fan_devices:
            if not device.writable():
                continue
            lower = device.min_rpm()
            upper = device.max_rpm()
            target = rpm
            if lower is not None and upper is not None:
                target = int(clamp(rpm, lower, upper))
            device.set_target(target)
            applied = target
        return applied

    def disable_manual_fan_control(self) -> None:
        for device in self._fan_devices:
            try:
                device.disable_manual()
            except OSError:
                continue

    def _discover_temp_paths(self) -> List[Path]:
        allowlist = [name.lower() for name in self.config["hardware"]["temp_name_allowlist"]]
        results: List[Path] = []
        for name_file in glob.glob("/sys/class/hwmon/*/name"):
            try:
                sensor_name = Path(name_file).read_text(encoding="utf-8").strip().lower()
            except OSError:
                continue
            if allowlist and sensor_name not in allowlist:
                continue
            hwmon_dir = Path(name_file).parent
            for temp_path in hwmon_dir.glob("temp*_input"):
                results.append(temp_path)

        if results:
            return sorted(results)

        for pattern in self.config["hardware"]["temp_input_globs"]:
            for item in glob.glob(pattern):
                results.append(Path(item))
        return sorted(set(results))

    def _discover_fans(self) -> List[FanDevice]:
        inputs: Dict[int, Path] = {}
        mins: Dict[int, Path] = {}
        maxs: Dict[int, Path] = {}
        targets: Dict[int, Path] = {}
        manuals: Dict[int, Path] = {}
        outputs: Dict[int, Path] = {}

        for item in self._glob_indexed(self.config["hardware"]["fan_input_globs"], "fan", "_input"):
            inputs[item[0]] = item[1]
        for item in self._glob_indexed(self.config["hardware"]["fan_min_globs"], "fan", "_min"):
            mins[item[0]] = item[1]
        for item in self._glob_indexed(self.config["hardware"]["fan_max_globs"], "fan", "_max"):
            maxs[item[0]] = item[1]
        for item in self._glob_indexed(self.config["hardware"]["fan_target_globs"], "fan", "_target"):
            targets[item[0]] = item[1]
        for item in self._glob_indexed(self.config["hardware"]["fan_manual_globs"], "fan", "_manual"):
            manuals[item[0]] = item[1]
        for item in self._glob_indexed(self.config["hardware"]["fan_output_globs"], "fan", "_output"):
            outputs[item[0]] = item[1]

        devices: List[FanDevice] = []
        for index in sorted(inputs):
            devices.append(
                FanDevice(
                    index=index,
                    input_path=inputs[index],
                    min_path=mins.get(index),
                    max_path=maxs.get(index),
                    target_path=targets.get(index),
                    manual_path=manuals.get(index),
                    output_path=outputs.get(index),
                )
            )
        return devices

    def _discover_keyboard_backlight(self) -> Optional[tuple[Path, Path]]:
        brightness = Path(self.config["hardware"]["keyboard_backlight_path"])
        maximum = Path(self.config["hardware"]["keyboard_backlight_max_path"])
        if brightness.exists() and maximum.exists():
            return brightness, maximum
        return None

    @staticmethod
    def _glob_indexed(patterns: List[str], prefix: str, suffix: str) -> List[tuple[int, Path]]:
        found: List[tuple[int, Path]] = []
        for pattern in patterns:
            for item in glob.glob(pattern):
                path = Path(item)
                name = path.name
                if not (name.startswith(prefix) and name.endswith(suffix)):
                    continue
                number = name[len(prefix): len(name) - len(suffix)]
                try:
                    index = int(number)
                except ValueError:
                    continue
                found.append((index, path))
        return found


class GuardianService:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self.lock = threading.RLock()
        self.config = self._load_config()
        self.hardware = HardwareManager(self.config)
        self.state: Dict[str, Any] = {
            "cpu_temp_c": None,
            "fan_rpm": [],
            "last_applied_rpm": None,
            "last_error": None,
            "console_blank_applied": None,
            "sensor_failures": 0,
            "updated_at": None,
            "started_at": time.time(),
        }
        self.stop_event = threading.Event()
        self.control_thread = threading.Thread(target=self._control_loop, name="guardian-control", daemon=True)

    def start(self) -> None:
        if self.config["backlight"]["disable_on_boot"]:
            try:
                self.hardware.disable_keyboard_backlight()
            except OSError as exc:
                logging.warning("disable keyboard backlight failed: %s", exc)
        else:
            try:
                self.hardware.set_keyboard_backlight(int(self.config["backlight"].get("boot_brightness", 0)))
            except (OSError, RuntimeError, ValueError) as exc:
                logging.warning("set keyboard backlight on boot failed: %s", exc)
        self.apply_console_blank()
        self.control_thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.control_thread.join(timeout=3)

    def status_snapshot(self) -> Dict[str, Any]:
        with self.lock:
            snapshot = {
                "cpu_temp_c": self.state["cpu_temp_c"],
                "fan_rpm": list(self.state["fan_rpm"]),
                "last_applied_rpm": self.state["last_applied_rpm"],
                "last_error": self.state["last_error"],
                "console_blank_applied": self.state["console_blank_applied"],
                "updated_at": self.state["updated_at"],
                "policy": copy.deepcopy(self.config["policy"]),
                "backlight_config": copy.deepcopy(self.config["backlight"]),
                "console_config": copy.deepcopy(self.config["console"]),
                "capabilities": self.hardware.capabilities(),
                "keyboard_backlight": self.hardware.keyboard_backlight_status(),
                "logo_backlight": {
                    "supported": False,
                    "reason": "no-independent-device",
                },
                "config_path": str(self.config_path),
            }
        bounds = self.hardware.computed_bounds()
        snapshot["detected_bounds"] = bounds
        return snapshot

    def update_policy(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            policy = self.config["policy"]
            for key in ("profile", "low_temp", "high_temp", "danger_temp", "min_rpm", "max_rpm", "poll_interval_sec"):
                if key not in payload:
                    continue
                policy[key] = payload[key]
            self._validate_policy(policy)
            self._save_config()
            status = self.status_snapshot()
        return status

    def update_keyboard_backlight(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        supported = self.hardware.capabilities()["keyboard_backlight_supported"]
        if not supported:
            raise ValueError("keyboard backlight is not supported on this host")

        with self.lock:
            backlight = self.config["backlight"]
            if "disable_on_boot" in payload:
                backlight["disable_on_boot"] = bool(payload["disable_on_boot"])

            brightness: Optional[int] = None
            if "brightness" in payload and payload["brightness"] is not None:
                brightness = int(payload["brightness"])
                applied = self.hardware.set_keyboard_backlight(brightness)
                backlight["boot_brightness"] = applied
                if applied > 0:
                    backlight["disable_on_boot"] = False

            if payload.get("enabled") is False:
                applied = self.hardware.set_keyboard_backlight(0)
                backlight["boot_brightness"] = applied
                backlight["disable_on_boot"] = True
            elif payload.get("enabled") is True and brightness is None:
                applied = self.hardware.set_keyboard_backlight(int(backlight.get("boot_brightness", 0)))
                if applied > 0:
                    backlight["disable_on_boot"] = False

            self._save_config()
            return self.status_snapshot()

    def update_console(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            console = self.config["console"]
            if "blank_enabled" in payload:
                console["blank_enabled"] = bool(payload["blank_enabled"])
            if "blank_minutes" in payload:
                console["blank_minutes"] = int(payload["blank_minutes"])
            self._validate_console(console)
            self._save_config()
            self.apply_console_blank()
            return self.status_snapshot()

    def _load_config(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            return copy.deepcopy(DEFAULT_CONFIG)
        loaded = read_json_file(self.config_path)
        return deep_merge(DEFAULT_CONFIG, loaded)

    def _save_config(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config_path.open("w", encoding="utf-8") as handle:
            json.dump(self.config, handle, ensure_ascii=False, indent=2)
            handle.write("\n")

    def _validate_policy(self, policy: Dict[str, Any]) -> None:
        low = float(policy["low_temp"])
        high = float(policy["high_temp"])
        danger = float(policy["danger_temp"])
        min_rpm = int(policy["min_rpm"])
        max_rpm = int(policy["max_rpm"])
        poll_interval = int(policy["poll_interval_sec"])

        if not (0 < low < high < danger):
            raise ValueError("temperature thresholds must satisfy low_temp < high_temp < danger_temp")
        if not (0 < min_rpm < max_rpm):
            raise ValueError("rpm thresholds must satisfy min_rpm < max_rpm")
        if not (1 <= poll_interval <= 60):
            raise ValueError("poll_interval_sec must be between 1 and 60")

    def _validate_console(self, console: Dict[str, Any]) -> None:
        blank_minutes = int(console["blank_minutes"])
        if not (0 <= blank_minutes <= 60):
            raise ValueError("console blank_minutes must be between 0 and 60")

    def apply_console_blank(self) -> None:
        console = self.config["console"]
        tty_path = console.get("tty_path", "/dev/tty0")
        blank_enabled = bool(console.get("blank_enabled", True))
        blank_minutes = int(console.get("blank_minutes", 1))

        if not os.path.exists(tty_path):
            with self.lock:
                self.state["console_blank_applied"] = False
                self.state["last_error"] = f"console-tty-missing: {tty_path}"
            return

        command = ["/usr/bin/setterm"]
        if blank_enabled:
            command.extend([
                "--blank", str(blank_minutes),
                "--powersave", "powerdown",
                "--powerdown", str(blank_minutes),
            ])
        else:
            command.extend([
                "--blank", "0",
                "--powersave", "off",
                "--powerdown", "0",
            ])

        try:
            env = os.environ.copy()
            env["TERM"] = "linux"
            with open(tty_path, "r", encoding="utf-8", errors="ignore") as tty_in, open(
                tty_path, "w", encoding="utf-8", errors="ignore"
            ) as tty_out:
                subprocess.run(
                    command,
                    stdin=tty_in,
                    stdout=tty_out,
                    stderr=subprocess.PIPE,
                    check=True,
                    text=True,
                    env=env,
                )
        except (OSError, subprocess.CalledProcessError) as exc:
            with self.lock:
                self.state["console_blank_applied"] = False
                self.state["last_error"] = f"console-blank-failed: {exc}"
            logging.warning("apply console blank failed: %s", exc)
            return

        with self.lock:
            self.state["console_blank_applied"] = True
            if self.state["last_error"] and str(self.state["last_error"]).startswith("console-"):
                self.state["last_error"] = None

    def _control_loop(self) -> None:
        while not self.stop_event.is_set():
            started = time.time()
            try:
                self._tick()
            except Exception as exc:  # pylint: disable=broad-except
                logging.exception("control loop failed: %s", exc)
                with self.lock:
                    self.state["last_error"] = str(exc)
            interval = int(self.config["policy"]["poll_interval_sec"])
            elapsed = time.time() - started
            time.sleep(max(0.1, interval - elapsed))

    def _tick(self) -> None:
        self.hardware.refresh()
        temp = self.hardware.read_cpu_temp_c()
        fans = self.hardware.read_fan_rpms()
        with self.lock:
            self.state["cpu_temp_c"] = temp
            self.state["fan_rpm"] = fans
            self.state["updated_at"] = int(time.time())

        if not self.config["policy"].get("enabled", True):
            self.hardware.disable_manual_fan_control()
            with self.lock:
                self.state["last_applied_rpm"] = None
                self.state["last_error"] = None
            return

        if temp is None:
            with self.lock:
                self.state["sensor_failures"] += 1
                self.state["last_error"] = "temperature-read-failed"
            return

        target = self._target_rpm(temp)
        if self.hardware.capabilities()["fan_control_supported"]:
            try:
                applied = self.hardware.set_all_fan_targets(target)
            except Exception as exc:  # pylint: disable=broad-except
                with self.lock:
                    self.state["last_error"] = f"fan-write-failed: {exc}"
                return
        else:
            applied = None

        with self.lock:
            self.state["sensor_failures"] = 0
            self.state["last_error"] = None
            self.state["last_applied_rpm"] = applied

    def _target_rpm(self, temp_c: float) -> int:
        policy = self.config["policy"]
        low = float(policy["low_temp"])
        high = float(policy["high_temp"])
        danger = float(policy["danger_temp"])
        min_rpm = int(policy["min_rpm"])
        max_rpm = int(policy["max_rpm"])

        if temp_c <= low:
            return min_rpm
        if temp_c >= danger:
            return max_rpm
        if temp_c < high:
            ratio = (temp_c - low) / (high - low)
            return int(round(min_rpm + ratio * (max_rpm - min_rpm) * 0.55))

        ratio = (temp_c - high) / (danger - high)
        return int(round(min_rpm + (max_rpm - min_rpm) * (0.55 + 0.45 * ratio)))


class GuardianRequestHandler(BaseHTTPRequestHandler):
    server_version = "MacNASGuardian/0.1"

    @property
    def app(self) -> GuardianService:
        return self.server.app  # type: ignore[attr-defined]

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/" or self.path == "/index.html":
            self._send_html(INDEX_HTML)
            return
        if self.path == "/api/v1/status":
            self._send_json(self.app.status_snapshot())
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/v1/fan-policy":
            payload = self._read_json_body()
            try:
                status = self.app.update_policy(payload)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(status)
            return
        if self.path == "/api/v1/backlight/keyboard":
            payload = self._read_json_body()
            try:
                status = self.app.update_keyboard_backlight(payload)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(status)
            return
        if self.path == "/api/v1/console":
            payload = self._read_json_body()
            try:
                status = self.app.update_console(payload)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(status)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, fmt: str, *args: Any) -> None:
        logging.info("%s - %s", self.address_string(), fmt % args)

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: Dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class GuardianHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], app: GuardianService) -> None:
        super().__init__(server_address, GuardianRequestHandler)
        self.daemon_threads = True
        self.block_on_close = False
        self.app = app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mac NAS Guardian agent")
    parser.add_argument(
        "--config",
        default=os.environ.get("GUARDIAN_CONFIG", "/etc/mac-nas-guardian/config.json"),
        help="path to config json",
    )
    parser.add_argument(
        "--write-default-config",
        action="store_true",
        help="write default config to the configured path and exit",
    )
    return parser.parse_args()


def run_server(app: GuardianService) -> None:
    host = app.config["server"]["listen_host"]
    port = int(app.config["server"]["listen_port"])
    httpd = GuardianHTTPServer((host, port), app)
    httpd.timeout = 0.5
    shutdown_requested = threading.Event()

    def handle_signal(signum: int, _frame: Any) -> None:
        logging.info("received signal %s, shutting down", signum)
        shutdown_requested.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    app.start()
    logging.info("listening on http://%s:%s", host, port)
    try:
        while not shutdown_requested.is_set():
            httpd.handle_request()
    finally:
        logging.info("stopping background workers")
        app.stop()
        logging.info("closing http server")
        httpd.server_close()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    config_path = Path(args.config)

    if args.write_default_config:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("w", encoding="utf-8") as handle:
            json.dump(DEFAULT_CONFIG, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        logging.info("default config written to %s", config_path)
        return 0

    app = GuardianService(config_path)
    run_server(app)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
