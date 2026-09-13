#!/usr/bin/env bash
case "${1:-status}" in
  start)
    systemctl --user start filebrowser.service
    echo "File Browser 已启动。"
    ;;
  stop)
    systemctl --user stop filebrowser.service
    echo "File Browser 已停止。"
    ;;
  restart)
    systemctl --user restart filebrowser.service
    echo "File Browser 已重启。"
    ;;
  status)
    systemctl --user status filebrowser.service --no-pager
    ;;
  logs)
    tail -n 50 /home/admin/logs/filebrowser.log
    ;;
  *)
    echo "用法: $0 {start|stop|restart|status|logs}"
    exit 1
    ;;
esac
