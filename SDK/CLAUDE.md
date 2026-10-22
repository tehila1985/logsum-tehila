# LogSum — standing instructions

- Log lines look like: `<ISO time> <LEVEL> <service> <message>`. Levels: DEBUG, INFO, WARN, ERROR.
- Files: `app.log` (OrderService, PaymentClient), `nginx.log` (HTTP access), `worker.log` (background jobs).
- Times in tool arguments are ISO, e.g. `2026-10-22T14:00`.
- Long-term memory lives behind the `remember` / `forget` / `recall` tools, not in this file.
