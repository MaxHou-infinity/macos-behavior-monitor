#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MacOS用户行为实时记录工具 - 单元测试

该模块包含对EventMonitor类的单元测试。
"""

import os
import json
import time
import unittest
import tempfile
from unittest.mock import patch, MagicMock
from event_monitor import EventMonitor


class TestEventMonitor(unittest.TestCase):
    """EventMonitor类的测试用例"""

    def setUp(self):
        """测试前的准备工作"""
        # 创建临时输出文件
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_path = os.path.join(self.temp_dir.name, "test_output.json")
        
        # 创建测试模式的监控器
        self.monitor = EventMonitor(
            test_mode=True,
            output_path=self.output_path,
            buffer_size=10,
            flush_interval=1.0,
            sampling_rate=1.0
        )

    def tearDown(self):
        """测试后的清理工作"""
        # 停止监控器
        if self.monitor.running:
            self.monitor.stop()
        
        # 清理临时文件
        self.temp_dir.cleanup()

    def test_initialization(self):
        """测试初始化参数"""
        self.assertTrue(self.monitor.test_mode)
        self.assertEqual(self.monitor.output_path, self.output_path)
        self.assertEqual(self.monitor.buffer_size, 10)
        self.assertEqual(self.monitor.flush_interval, 1.0)
        self.assertEqual(self.monitor.sampling_rate, 1.0)
        self.assertFalse(self.monitor.running)
        self.assertEqual(self.monitor.event_count, 0)
        self.assertEqual(len(self.monitor.event_buffer), 0)

    def test_start_stop(self):
        """测试启动和停止功能"""
        # 启动监控器
        result = self.monitor.start()
        self.assertTrue(result)
        self.assertTrue(self.monitor.running)
        
        # 停止监控器
        result = self.monitor.stop()
        self.assertTrue(result)
        self.assertFalse(self.monitor.running)

    def test_add_event(self):
        """测试添加事件功能"""
        # 添加测试事件
        self.monitor._add_event("test_event", {"test_data": "value"})
        
        # 验证事件是否添加到缓冲区
        self.assertEqual(len(self.monitor.event_buffer), 1)
        self.assertEqual(self.monitor.event_count, 1)
        
        # 验证事件内容
        event = self.monitor.event_buffer[0]
        self.assertEqual(event["type"], "test_event")
        self.assertEqual(event["test_data"], "value")
        self.assertIn("timestamp", event)
        self.assertIn("window", event)

    def test_flush_buffer(self):
        """测试刷新缓冲区功能"""
        # 添加多个测试事件
        for i in range(5):
            self.monitor._add_event("test_event", {"index": i})
        
        # 手动刷新缓冲区
        self.monitor._flush_buffer()
        
        # 验证缓冲区已清空
        self.assertEqual(len(self.monitor.event_buffer), 0)
        
        # 验证文件是否创建
        self.assertTrue(os.path.exists(self.output_path))
        
        # 验证文件内容
        with open(self.output_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            self.assertIn("events", data)
            self.assertEqual(len(data["events"]), 5)
            for i, event in enumerate(data["events"]):
                self.assertEqual(event["type"], "test_event")
                self.assertEqual(event["index"], i)

    def test_get_events(self):
        """测试获取事件功能"""
        # 添加多个测试事件
        for i in range(20):
            self.monitor._add_event("test_event", {"index": i})
        
        # 获取最新的10个事件
        events = self.monitor.get_events(limit=10)
        
        # 验证返回的事件数量
        self.assertEqual(len(events), 10)
        
        # 验证返回的是最新的事件
        for i, event in enumerate(events):
            self.assertEqual(event["index"], i + 10)

    def test_get_status(self):
        """测试获取状态功能"""
        status = self.monitor.get_status()
        
        # 验证状态信息
        self.assertIn("running", status)
        self.assertIn("test_mode", status)
        self.assertIn("event_count", status)
        self.assertIn("buffer_size", status)
        self.assertIn("output_path", status)
        self.assertIn("flush_interval", status)
        self.assertIn("filter_sensitive", status)
        self.assertIn("encryption", status)
        self.assertIn("sampling_rate", status)

    @patch('event_monitor.mouse')
    @patch('event_monitor.keyboard')
    def test_real_mode_start(self, mock_keyboard, mock_mouse):
        """测试真实模式启动功能"""
        # 创建模拟的监听器
        mock_mouse_listener = MagicMock()
        mock_keyboard_listener = MagicMock()
        mock_mouse.Listener.return_value = mock_mouse_listener
        mock_keyboard.Listener.return_value = mock_keyboard_listener
        
        # 创建真实模式的监控器
        real_monitor = EventMonitor(
            test_mode=False,
            output_path=self.output_path
        )
        
        # 启动监控器
        with patch('event_monitor.PYNPUT_AVAILABLE', True):
            result = real_monitor.start()
            
            # 验证结果
            self.assertTrue(result)
            self.assertTrue(real_monitor.running)
            
            # 验证监听器是否启动
            mock_mouse.Listener.assert_called_once()
            mock_keyboard.Listener.assert_called_once()
            mock_mouse_listener.start.assert_called_once()
            mock_keyboard_listener.start.assert_called_once()
            
            # 停止监控器
            real_monitor.stop()


if __name__ == '__main__':
    unittest.main() 