#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MacOS用户行为实时记录工具 - Web应用程序

该模块提供了一个Web界面，用于控制事件监控器和查看捕获的事件数据。
支持实时数据显示、配置调整和数据导出功能。
"""

import os
import json
import time
import uuid
import logging
import argparse
import datetime
import secrets
from threading import Lock
from flask import Flask, render_template, request, jsonify, send_file, session
from flask_socketio import SocketIO
from event_monitor import EventMonitor

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('web_app.log', encoding='utf-8')
    ]
)
logger = logging.getLogger("web_app")

# 创建Flask应用
app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(32)  # 使用随机密钥
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(hours=5)

# 配置CORS
socketio = SocketIO(app, cors_allowed_origins="*")  # 在生产环境中应限制来源

# 全局变量
monitor = None
monitor_lock = Lock()
latest_events = []
client_sessions = {}

# 默认配置
default_config = {
    "test_mode": True,
    "output_path": "./output.json",
    "encryption": False,
    "filter_sensitive": True,
    "buffer_size": 1000,
    "flush_interval": 10.0,
    "sampling_rate": 1.0
}

@app.route('/')
def index():
    """渲染主页"""
    # 为每个会话生成唯一ID
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    
    return render_template('index.html')

@app.route('/api/status', methods=['GET'])
def get_status():
    """获取监控器状态"""
    global monitor
    
    with monitor_lock:
        if monitor:
            return jsonify(monitor.get_status())
        else:
            return jsonify({
                "running": False,
                "test_mode": default_config["test_mode"],
                "event_count": 0,
                "buffer_size": 0,
                "output_path": default_config["output_path"],
                "flush_interval": default_config["flush_interval"],
                "filter_sensitive": default_config["filter_sensitive"],
                "encryption": default_config["encryption"],
                "sampling_rate": default_config["sampling_rate"]
            })

@app.route('/api/start', methods=['POST'])
def start_monitor():
    """启动监控器"""
    global monitor
    
    # 获取配置参数
    config = request.json or {}
    
    # 合并默认配置和用户配置
    monitor_config = default_config.copy()
    for key in monitor_config:
        if key in config:
            monitor_config[key] = config[key]
    
    # 验证参数
    try:
        monitor_config["flush_interval"] = float(monitor_config["flush_interval"])
        if monitor_config["flush_interval"] < 1.0:
            return jsonify({"success": False, "error": "采样间隔必须至少为1.0秒"}), 400
            
        monitor_config["buffer_size"] = int(monitor_config["buffer_size"])
        if monitor_config["buffer_size"] < 10:
            return jsonify({"success": False, "error": "缓冲区大小必须至少为10"}), 400
            
        monitor_config["sampling_rate"] = float(monitor_config["sampling_rate"])
        if monitor_config["sampling_rate"] < 0.01 or monitor_config["sampling_rate"] > 1.0:
            return jsonify({"success": False, "error": "采样率必须在0.01到1.0之间"}), 400
    except (ValueError, TypeError) as e:
        return jsonify({"success": False, "error": f"参数验证失败: {str(e)}"}), 400
    
    with monitor_lock:
        # 如果监控器已经在运行，先停止它
        if monitor and monitor.running:
            monitor.stop()
            logger.info("已停止现有监控器")
        
        try:
            # 创建新的监控器
            monitor = EventMonitor(
                test_mode=monitor_config["test_mode"],
                output_path=monitor_config["output_path"],
                encryption=monitor_config["encryption"],
                filter_sensitive=monitor_config["filter_sensitive"],
                buffer_size=monitor_config["buffer_size"],
                flush_interval=monitor_config["flush_interval"],
                sampling_rate=monitor_config["sampling_rate"]
            )
            
            # 启动监控器
            success = monitor.start()
            
            if success:
                # 启动事件推送线程
                socketio.start_background_task(push_events)
                logger.info(f"监控器已启动，配置: {monitor_config}")
                return jsonify({
                    "success": True, 
                    "message": "监控器已启动",
                    "config": monitor_config
                })
            else:
                logger.error("启动监控器失败")
                return jsonify({"success": False, "error": "启动监控器失败"}), 500
        except Exception as e:
            logger.error(f"创建或启动监控器时出错: {str(e)}")
            return jsonify({"success": False, "error": f"启动失败: {str(e)}"}), 500

@app.route('/api/stop', methods=['POST'])
def stop_monitor():
    """停止监控器"""
    global monitor
    
    with monitor_lock:
        if monitor and monitor.running:
            try:
                monitor.stop()
                event_count = monitor.event_count
                logger.info(f"监控器已停止，共记录{event_count}个事件")
                return jsonify({
                    "success": True, 
                    "message": "监控器已停止", 
                    "event_count": event_count
                })
            except Exception as e:
                logger.error(f"停止监控器时出错: {str(e)}")
                return jsonify({"success": False, "error": f"停止失败: {str(e)}"}), 500
        else:
            return jsonify({"success": False, "error": "监控器未运行"}), 400

@app.route('/api/events', methods=['GET'])
def get_events():
    """获取当前事件"""
    global monitor, latest_events
    
    # 获取请求的事件数量
    limit = request.args.get('limit', default=10, type=int)
    limit = max(1, min(limit, 100))  # 限制在1-100之间
    
    with monitor_lock:
        if monitor and monitor.running:
            try:
                events = monitor.get_events(limit=limit)
                latest_events = events  # 更新最新事件
                return jsonify({"success": True, "events": events})
            except Exception as e:
                logger.error(f"获取事件时出错: {str(e)}")
                return jsonify({"success": False, "error": f"获取事件失败: {str(e)}"}), 500
        else:
            return jsonify({"success": True, "events": latest_events})

@app.route('/api/save', methods=['POST'])
def save_events():
    """保存事件数据到文件"""
    global monitor
    
    # 获取文件名参数
    data = request.json or {}
    filename = data.get("filename", "")
    
    # 如果没有提供文件名，使用时间戳生成
    if not filename:
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"{timestamp}-monitor.json"
    
    # 确保文件名有.json后缀
    if not filename.endswith(".json"):
        filename += ".json"
    
    # 验证文件名安全性
    if not is_safe_filename(filename):
        return jsonify({"success": False, "error": "不安全的文件名"}), 400
    
    # 文件路径
    file_path = os.path.join(os.getcwd(), filename)
    
    with monitor_lock:
        if monitor:
            try:
                # 强制刷新缓冲区
                monitor._flush_buffer()
                
                # 复制输出文件到指定文件名
                try:
                    with open(monitor.output_path, 'r', encoding='utf-8') as src:
                        if monitor.encryption and monitor.encryption_key:
                            from cryptography.fernet import Fernet
                            fernet = Fernet(monitor.encryption_key)
                            content = src.read()
                            content = fernet.decrypt(content.encode()).decode('utf-8')
                            data = json.loads(content)
                        else:
                            data = json.load(src)
                    
                    with open(file_path, 'w', encoding='utf-8') as dst:
                        json.dump(data, dst, ensure_ascii=False, indent=2)
                    
                    logger.info(f"已保存事件数据到: {file_path}")
                    return jsonify({
                        "success": True, 
                        "filename": filename, 
                        "path": file_path,
                        "event_count": len(data["events"])
                    })
                except Exception as e:
                    logger.error(f"保存事件数据失败: {str(e)}")
                    return jsonify({"success": False, "error": f"保存事件数据失败: {str(e)}"}), 500
            except Exception as e:
                logger.error(f"刷新缓冲区失败: {str(e)}")
                return jsonify({"success": False, "error": f"刷新缓冲区失败: {str(e)}"}), 500
        else:
            return jsonify({"success": False, "error": "监控器未初始化"}), 400

@app.route('/api/download/<filename>', methods=['GET'])
def download_file(filename):
    """下载事件数据文件"""
    # 验证文件名安全性
    if not is_safe_filename(filename):
        return jsonify({"success": False, "error": "不安全的文件名"}), 400
    
    file_path = os.path.join(os.getcwd(), filename)
    
    if os.path.exists(file_path):
        try:
            return send_file(file_path, as_attachment=True)
        except Exception as e:
            logger.error(f"下载文件失败: {str(e)}")
            return jsonify({"success": False, "error": f"下载文件失败: {str(e)}"}), 500
    else:
        return jsonify({"success": False, "error": "文件不存在"}), 404

@app.route('/api/config', methods=['GET'])
def get_config():
    """获取当前配置"""
    global monitor, default_config
    
    with monitor_lock:
        if monitor:
            return jsonify({
                "success": True,
                "config": monitor.get_status()
            })
        else:
            return jsonify({
                "success": True,
                "config": default_config
            })

@app.route('/api/update_interval', methods=['POST'])
def update_interval():
    """更新采样间隔"""
    global monitor
    
    data = request.json or {}
    new_interval = data.get("interval", 10.0)
    
    try:
        new_interval = float(new_interval)
        if new_interval < 1.0:
            return jsonify({"success": False, "error": "采样间隔必须至少为1.0秒"}), 400
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "无效的采样间隔值"}), 400
    
    with monitor_lock:
        if monitor:
            # 更新监控器的采样间隔
            monitor.flush_interval = new_interval
            logger.info(f"已更新采样间隔为: {new_interval}秒")
            return jsonify({
                "success": True,
                "message": f"已更新采样间隔为: {new_interval}秒",
                "interval": new_interval
            })
        else:
            # 如果监控器未初始化，更新默认配置
            default_config["flush_interval"] = new_interval
            logger.info(f"已更新默认采样间隔为: {new_interval}秒")
            return jsonify({
                "success": True,
                "message": f"已更新默认采样间隔为: {new_interval}秒",
                "interval": new_interval
            })

@socketio.on('connect')
def handle_connect():
    """处理客户端连接"""
    client_id = request.sid
    session_id = session.get('session_id', str(uuid.uuid4()))
    client_sessions[client_id] = session_id
    logger.debug(f"客户端连接: {client_id}, 会话: {session_id}")

@socketio.on('disconnect')
def handle_disconnect():
    """处理客户端断开连接"""
    client_id = request.sid
    if client_id in client_sessions:
        del client_sessions[client_id]
        logger.debug(f"客户端断开连接: {client_id}")

def push_events():
    """推送事件到客户端的后台任务"""
    global monitor
    
    while True:
        with monitor_lock:
            if not monitor or not monitor.running:
                break
            
            try:
                # 获取最新事件
                events = monitor.get_events(limit=10)
                if events:
                    # 发送事件到客户端
                    socketio.emit('events_update', {"events": events})
                    
                    # 发送状态更新
                    status = monitor.get_status()
                    socketio.emit('status_update', status)
            except Exception as e:
                logger.error(f"推送事件时出错: {str(e)}")
        
        # 等待一段时间再次推送
        socketio.sleep(1)

def is_safe_filename(filename):
    """检查文件名是否安全"""
    # 禁止路径遍历
    if '..' in filename or '/' in filename or '\\' in filename:
        return False
    
    # 只允许字母、数字、下划线、连字符、点和某些特殊字符
    import re
    if not re.match(r'^[a-zA-Z0-9_\-\.]+$', filename):
        return False
    
    return True

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="MacOS用户行为实时记录工具 - Web界面",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument(
        "--host", 
        type=str, 
        default="127.0.0.1",
        help="Web服务器主机地址"
    )
    
    parser.add_argument(
        "--port", 
        type=int, 
        default=5000,
        help="Web服务器端口"
    )
    
    parser.add_argument(
        "--debug", 
        action="store_true",
        help="启用调试模式"
    )
    
    parser.add_argument(
        "--log_level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="日志级别"
    )
    
    return parser.parse_args()

def setup_logging(log_level):
    """设置日志级别"""
    level = getattr(logging, log_level)
    for handler in logging.root.handlers:
        handler.setLevel(level)
    logging.root.setLevel(level)
    logger.setLevel(level)
    logger.info(f"日志级别设置为: {log_level}")

def main():
    """主函数"""
    # 解析命令行参数
    args = parse_args()
    
    # 设置日志级别
    setup_logging(args.log_level)
    
    # 检查系统
    import platform
    if platform.system() != "Darwin":
        logger.warning("此工具主要为MacOS设计，在其他系统上可能无法正常工作")
    
    # 启动Web服务器
    logger.info(f"启动Web服务器: {args.host}:{args.port}")
    socketio.run(app, host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()