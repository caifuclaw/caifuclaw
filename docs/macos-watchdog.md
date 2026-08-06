# macOS 本机服务守护

watchdog 负责业务服务与连接器运行时：

```text
caifuclaw-business-api      http://127.0.0.1:9999/health
connector-runtime-api   http://127.0.0.1:8100/health
```

安装并立即启动：

```bash
chmod +x deploy/macos/*.sh
deploy/macos/install_caifuclaw_erp_launchd.sh
```

查看日志：

```bash
tail -f logs/watchdog/watchdog.log
```

卸载：

```bash
deploy/macos/uninstall_caifuclaw_erp_launchd.sh
```

业务前端由业务 API 托管。watchdog 会在源码比 `dist` 新或静态资源缺失时重新构建前端，然后再检查服务健康状态。
