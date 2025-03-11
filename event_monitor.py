#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MacOS用户行为实时记录工具 - 事件监控模块

该模块负责捕获用户的鼠标和键盘事件，并记录相关的窗口上下文信息。
支持正常模式和测试模式两种运行方式。
"""

import os
import time
import json
import random
import datetime
import threading
import logging
import base64
import hashlib
import subprocess
from typing import Dict, List, Any, Optional, Tuple, Union
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("event_monitor")

# 检查是否可以导入必要的库
NATIVE_API_AVAILABLE = False
try:
    # 尝试导入 pyobjc 相关库
    import objc
    import Quartz
    NATIVE_API_AVAILABLE = True
    logger.info("成功导入 pyobjc 库")
except ImportError as e:
    logger.warning(f"无法导入 pyobjc 库: {e}")
    logger.warning("将使用测试模式或有限功能模式")


class EventMonitor:
    """事件监控类，负责捕获和处理用户行为事件"""
    
    def __init__(self, 
                 test_mode: bool = False,
                 output_path: str = "./output.json",
                 encryption: bool = False,
                 filter_sensitive: bool = True,
                 buffer_size: int = 1000,
                 flush_interval: float = 10.0,
                 sampling_rate: float = 1.0):
        """
        初始化事件监控器
        
        Args:
            test_mode: 是否使用测试模式
            output_path: 输出文件路径
            encryption: 是否加密输出文件
            filter_sensitive: 是否过滤敏感信息
            buffer_size: 事件缓冲区大小
            flush_interval: 写入文件的间隔时间（秒）
            sampling_rate: 事件采样率 (0.01-1.0)
        """
        self.test_mode = test_mode
        self.output_path = output_path
        self.encryption = encryption
        self.filter_sensitive = filter_sensitive
        self.buffer_size = max(10, buffer_size)
        self.flush_interval = max(1.0, flush_interval)
        self.sampling_rate = max(0.01, min(1.0, sampling_rate))
        
        self.event_buffer: List[Dict[str, Any]] = []
        self.event_count = 0
        self.running = False
        self.flush_thread = None
        self.test_thread = None
        self.event_thread = None
        self.last_sample_time = 0  # 上次采样时间
        
        # 如果没有必要的库，强制使用测试模式
        if not NATIVE_API_AVAILABLE and not self.test_mode:
            logger.warning("由于缺少必要的库，强制使用测试模式")
            self.test_mode = True
        
        # 加密相关
        self.encryption_key = None
        if self.encryption:
            self._setup_encryption()
        
        logger.info(f"事件监控器初始化完成，{'测试' if test_mode else '正常'}模式")
        logger.info(f"输出路径: {output_path}, 采样间隔: {flush_interval}秒")
    
    def _setup_encryption(self):
        """设置加密密钥"""
        try:
            # 使用机器特定信息生成密钥
            salt = b'macos_behavior_tracker_salt'
            password = hashlib.md5(os.uname().nodename.encode()).hexdigest().encode()
            
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(password))
            self.encryption_key = key
            logger.info("加密设置完成")
        except Exception as e:
            logger.error(f"设置加密失败: {e}")
            self.encryption = False

    def _add_event(self, event_type: str, event_data: Dict[str, Any]):
        """添加事件到缓冲区"""
        # 检查是否到达采样时间
        current_time = time.time()
        if current_time - self.last_sample_time < self.flush_interval:
            return
            
        # 更新上次采样时间
        self.last_sample_time = current_time
        
        # 应用采样率
        if random.random() > self.sampling_rate:
            return
            
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        window_info = self._get_window_info()
        
        event = {
            "type": event_type,
            "timestamp": timestamp,
            "screen_id": 0,
            "window": window_info
        }
        
        event.update(event_data)
        self.event_buffer.append(event)
        self.event_count += 1
        
        logger.info(f"记录事件: {event_type}, 时间: {timestamp}")
        
        if len(self.event_buffer) >= self.buffer_size:
            self._flush_buffer()

    def _get_window_info(self) -> Dict[str, Any]:
        """获取当前活动窗口信息"""
        if self.test_mode or not NATIVE_API_AVAILABLE:
            apps = ["Safari", "Finder", "Terminal", "Notes", "Mail", "Messages", "Calendar", "VSCode", "Chrome", "Slack"]
            titles = [
                "Google - Safari", 
                "Documents", 
                "Terminal — bash", 
                "Meeting Notes", 
                "Inbox (10)", 
                "Chat with Alex", 
                "March 2025",
                "event_monitor.py - Project",
                "GitHub - Chrome",
                "Team Channel - Slack"
            ]
            app_idx = random.randint(0, len(apps) - 1)
            return {
                "window_id": str(random.randint(1000, 9999)),
                "app_name": apps[app_idx],
                "window_title": titles[app_idx]
            }
        
        try:
            window_list = Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionOnScreenOnly, 
                Quartz.kCGNullWindowID)
            
            active_window = None
            min_layer = float('inf')
            
            for window in window_list:
                layer = window.get('kCGWindowLayer', float('inf'))
                if layer < min_layer:
                    active_window = window
                    min_layer = layer
            
            if active_window:
                window_id = active_window.get('kCGWindowNumber', 0)
                app_name = active_window.get('kCGWindowOwnerName', '')
                window_title = active_window.get('kCGWindowName', '')
                
                if self.filter_sensitive and any(s in window_title.lower() for s in 
                    ['password', 'login', 'credit', 'bank', 'secret', 'private', '密码', '登录', '银行']):
                    window_title = "[敏感内容已过滤]"
                
                return {
                    "window_id": str(window_id),
                    "app_name": app_name,
                    "window_title": window_title
                }
            
            return {
                "window_id": "0",
                "app_name": "Unknown",
                "window_title": "Unknown"
            }
        except Exception as e:
            logger.error(f"获取窗口信息失败: {str(e)}")
            return {
                "window_id": "0",
                "app_name": "Error",
                "window_title": f"Error: {str(e)[:50]}"
            }

    def start(self):
        """启动事件监控"""
        if self.running:
            logger.warning("监控器已经在运行中")
            return False
        
        self.running = True
        self.event_buffer = []
        self.event_count = 0
        self.last_sample_time = 0  # 重置上次采样时间
        
        # 启动刷新线程
        self.flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self.flush_thread.start()
        
        if self.test_mode:
            # 测试模式：生成模拟事件
            logger.info("启动测试模式，生成模拟事件")
            self.test_thread = threading.Thread(target=self._generate_test_events, daemon=True)
            self.test_thread.start()
        else:
            # 正常模式：监听真实事件
            if not NATIVE_API_AVAILABLE:
                logger.error("无法启动正常模式：缺少必要的库")
                self.running = False
                return False
            
            logger.info("启动正常模式，监听真实事件")
            try:
                # 检查cliclick是否可用
                try:
                    subprocess.run(["which", "cliclick"], check=True, capture_output=True)
                except subprocess.CalledProcessError:
                    logger.error("未找到cliclick工具，请先安装: brew install cliclick")
                    self.running = False
                    return False
                
                # 启动事件监听线程
                self.event_thread = threading.Thread(target=self._start_event_monitoring, daemon=True)
                self.event_thread.start()
                logger.info("事件监听器启动成功")
            except Exception as e:
                logger.error(f"启动监听器失败: {str(e)}")
                self.running = False
                return False
        
        logger.info("事件监控器启动成功")
        return True
    
    def _start_event_monitoring(self):
        """启动事件监听（使用原生API）"""
        try:
            # 使用cliclick工具模拟事件监听
            self._start_cliclick_monitoring()
        except Exception as e:
            logger.error(f"启动事件监听失败: {str(e)}")
    
    def _start_cliclick_monitoring(self):
        """使用cliclick工具监听鼠标位置"""
        logger.info("使用cliclick监听鼠标位置")
        
        last_pos = None
        
        while self.running:
            try:
                # 获取当前鼠标位置
                result = subprocess.run(["cliclick", "p"], capture_output=True, text=True, check=True)
                pos_str = result.stdout.strip()
                
                # 解析位置
                if "," in pos_str:
                    x_str, y_str = pos_str.split(",")
                    try:
                        x = float(x_str)
                        y = float(y_str)
                        
                        # 记录鼠标位置（采样间隔由_add_event控制）
                        if last_pos is None or (x != last_pos[0] or y != last_pos[1]):
                            self._add_event("mouse_move", {
                                "position": {"x": x, "y": y}
                            })
                            last_pos = (x, y)
                    except ValueError as e:
                        logger.error(f"解析鼠标位置失败: {str(e)}, 原始数据: {pos_str}")
                
                # 等待一小段时间
                time.sleep(1.0)  # 降低检查频率，减少CPU使用
            except Exception as e:
                logger.error(f"监听鼠标位置失败: {str(e)}")
                time.sleep(2.0)  # 出错后等待较长时间再重试
    
    def stop(self):
        """停止事件监控"""
        if not self.running:
            logger.warning("监控器已经停止")
            return False
        
        self.running = False
        
        # 等待线程结束
        if self.flush_thread:
            self._flush_buffer()  # 最后一次刷新
            self.flush_thread.join(timeout=2.0)
        
        if self.test_thread:
            self.test_thread.join(timeout=2.0)
        
        if self.event_thread:
            self.event_thread.join(timeout=2.0)
        
        logger.info(f"事件监控器已停止，共记录{self.event_count}个事件")
        return True
    
    def get_status(self) -> Dict[str, Any]:
        """获取监控器状态"""
        return {
            "running": self.running,
            "test_mode": self.test_mode,
            "event_count": self.event_count,
            "buffer_size": len(self.event_buffer),
            "output_path": self.output_path,
            "flush_interval": self.flush_interval,
            "filter_sensitive": self.filter_sensitive,
            "encryption": self.encryption,
            "sampling_rate": self.sampling_rate
        }
    
    def get_events(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最新事件"""
        return self.event_buffer[-limit:] if self.event_buffer else []
    
    def _flush_loop(self):
        """定期刷新缓冲区的循环"""
        while self.running:
            time.sleep(self.flush_interval)
            if self.running:  # 再次检查，避免在睡眠期间状态改变
                self._flush_buffer()
    
    def _flush_buffer(self):
        """将缓冲区内容写入文件"""
        if not self.event_buffer:
            return
        
        try:
            # 准备数据
            data = {"events": self.event_buffer.copy()}
            self.event_buffer = []
            
            # 确保输出目录存在
            output_dir = os.path.dirname(os.path.abspath(self.output_path))
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)
            
            # 读取现有数据（如果有）
            existing_data = {"events": []}
            if os.path.exists(self.output_path) and os.path.getsize(self.output_path) > 0:
                try:
                    with open(self.output_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if self.encryption and self.encryption_key:
                            # 解密内容
                            fernet = Fernet(self.encryption_key)
                            content = fernet.decrypt(content.encode()).decode('utf-8')
                        existing_data = json.loads(content)
                except Exception as e:
                    logger.error(f"读取现有数据失败: {str(e)}")
            
            # 合并数据
            existing_data["events"].extend(data["events"])
            
            # 写入文件
            content = json.dumps(existing_data, ensure_ascii=False, indent=2)
            
            if self.encryption and self.encryption_key:
                # 加密内容
                fernet = Fernet(self.encryption_key)
                content = fernet.encrypt(content.encode()).decode('utf-8')
            
            with open(self.output_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"已写入{len(data['events'])}个事件到{self.output_path}")
        except Exception as e:
            logger.error(f"写入文件失败: {str(e)}")
            # 恢复缓冲区
            self.event_buffer.extend(data["events"])
    
    # 测试模式事件生成
    def _generate_test_events(self):
        """生成测试事件"""
        event_types = ["mouse_move", "mouse_click", "key_press", "key_release", "mouse_scroll"]
        buttons = ["left", "right", "middle"]
        key_names = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m", 
                    "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z",
                    "space", "enter", "esc", "tab", "shift", "ctrl", "alt", "cmd"]
        
        screen_width, screen_height = 1920, 1080  # 假设的屏幕尺寸
        
        while self.running:
            # 随机选择事件类型
            event_type = random.choice(event_types)
            
            # 生成随机位置
            x = random.uniform(0, screen_width)
            y = random.uniform(0, screen_height)
            
            if event_type == "mouse_move":
                self._add_event("mouse_move", {
                    "position": {"x": x, "y": y}
                })
            
            elif event_type == "mouse_click":
                button = random.choice(buttons)
                state = random.choice(["pressed", "released"])
                self._add_event("mouse_click", {
                    "position": {"x": x, "y": y},
                    "button": button,
                    "state": state
                })
            
            elif event_type == "mouse_scroll":
                dx = random.uniform(-10, 10)
                dy = random.uniform(-10, 10)
                self._add_event("mouse_scroll", {
                    "position": {"x": x, "y": y},
                    "scroll_dx": dx,
                    "scroll_dy": dy
                })
            
            elif event_type == "key_press":
                key_name = random.choice(key_names)
                key_code = random.randint(1, 100)
                self._add_event("key_press", {
                    "key_code": key_code,
                    "key_name": key_name,
                    "state": "pressed",
                    "modifiers": []
                })
            
            elif event_type == "key_release":
                key_name = random.choice(key_names)
                key_code = random.randint(1, 100)
                self._add_event("key_release", {
                    "key_code": key_code,
                    "key_name": key_name,
                    "state": "released",
                    "modifiers": []
                })
            
            # 等待一段时间，与采样间隔相同
            time.sleep(self.flush_interval)
    