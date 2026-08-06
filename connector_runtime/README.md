# Connector Runtime

公共平台连接器运行时，负责平台 API 适配、字段标准化、状态更新、发货和面单下载。

启动：

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8100
```

业务应用通过 HTTP 调用本服务，不直接 import 平台连接器实现。
