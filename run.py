#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MacOS用户行为实时记录工具 - 主程序

该模块是程序的入口点，负责解析命令行参数并启动事件监控器。
支持正常模式和测试模式两种运行方式。
"""

import os
import sys
import argparse
import logging
import platform
import subprocess
from event_monitor import EventMonitor

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('monitor.log', encoding='utf-8')
    ]
)
logger = logging.getLogger("run")


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="MacOS用户行为实时记录工具",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument(
        "--test_mode", 
        action="store_true",
        help="使用测试模式（无需辅助功能权限）"
    )
    
    parser.add_argument(
        "--output_path", 
        type=str, 
        default="./output.json",
        help="输出文件路径"
    )
    
    parser.add_argument(
        "--sampling_rate", 
        type=float, 
        default=1.0,
        help="事件采样率 (0.01-1.0)"
    )
    
    parser.add_argument(
        "--encryption", 
        action="store_true",
        help="是否加密输出文件"
    )
    
    parser.add_argument(
        "--filter_sensitive", 
        action="store_true", 
        default=True,
        help="是否过滤敏感信息"
    )
    
    parser.add_argument(
        "--buffer_size", 
        type=int, 
        default=1000,
        help="事件缓冲区大小"
    )
    
    parser.add_argument(
        "--flush_interval", 
        type=float, 
        default=10.0,
        help="写入文件的间隔时间（秒）"
    )
    
    parser.add_argument(
        "--log_level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="日志级别"
    )
    
    args = parser.parse_args()
    
    # 验证参数
    if args.sampling_rate < 0.01 or args.sampling_rate > 1.0:
        parser.error("采样率必须在0.01到1.0之间")
    
    if args.buffer_size < 10:
        parser.error("缓冲区大小必须至少为10")
    
    if args.flush_interval < 1.0:
        parser.error("刷新间隔必须至少为1.0秒")
    
    return args


def check_macos():
    """检查是否为MacOS系统"""
    if platform.system() != "Darwin":
        logger.error("此工具仅支持MacOS系统")
        return False
    return True


def check_permissions():
    """检查辅助功能权限（仅在非测试模式下）"""
    try:
        # 检查cliclick工具是否已安装
        try:
            subprocess.run(["which", "cliclick"], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            logger.error("未找到cliclick工具，请先安装: brew install cliclick")
            return False
        
        # 检查是否可以获取鼠标位置
        try:
            result = subprocess.run(["cliclick", "p"], capture_output=True, text=True, check=True)
            if "," not in result.stdout:
                logger.error("无法获取鼠标位置，请检查权限")
                return False
        except subprocess.CalledProcessError as e:
            logger.error(f"执行cliclick失败: {e}")
            return False
        
        # 检查Quartz库
        try:
            from Quartz import CGWindowListCopyWindowInfo
            window_list = CGWindowListCopyWindowInfo(0, 0)
            if window_list is None:
                logger.error("无法获取窗口信息，请检查权限")
                return False
        except Exception as e:
            logger.error(f"Quartz库检查失败: {str(e)}")
            return False
        
        return True
    except Exception as e:
        logger.error(f"权限检查失败: {str(e)}")
        return False


def check_dependencies():
    """检查依赖库是否已安装"""
    required_packages = ["pyobjc", "cryptography"]
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package.replace("-", "_").split(".")[0])
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        logger.error(f"缺少必要的依赖库: {', '.join(missing_packages)}")
        logger.info("请安装缺失的依赖: pip install " + " ".join(missing_packages))
        return False
    
    # 检查cliclick工具
    try:
        subprocess.run(["which", "cliclick"], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        logger.error("未找到cliclick工具")
        logger.info("请安装cliclick: brew install cliclick")
        return False
    
    return True


def print_permission_instructions():
    """打印获取辅助功能权限的说明"""
    print("\n" + "=" * 80)
    print("需要辅助功能权限")
    print("=" * 80)
    print("要使用此工具捕获真实事件，您需要授予必要的权限。请按照以下步骤操作：")
    print("\n1. 安装cliclick工具（如果尚未安装）:")
    print("   brew install cliclick")
    print("\n2. 打开系统偏好设置（或系统设置）")
    print('3. 点击"安全性与隐私"（或"隐私与安全性"）')
    print('4. 选择"隐私"选项卡')
    print('5. 在左侧列表中选择"辅助功能"')
    print("6. 点击锁图标并输入密码以进行更改")
    print('7. 点击"+"按钮添加Terminal（或您使用的终端应用）')
    print('8. 确保Terminal旁边的复选框已勾选')
    print("\n如果不想授予权限，可以使用--test_mode参数在测试模式下运行程序。")
    print("=" * 80 + "\n")


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
    if not check_macos():
        return 1
    
    # 如果不是测试模式，检查依赖和权限
    if not args.test_mode:
        if not check_dependencies():
            logger.error("依赖检查失败，请安装所有必要的依赖")
            return 1
        
        if not check_permissions():
            print_permission_instructions()
            logger.warning("未获得必要权限，请授予权限或使用测试模式")
            return 1
    
    # 创建输出目录（如果不存在）
    output_dir = os.path.dirname(os.path.abspath(args.output_path))
    if output_dir and not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir, exist_ok=True)
            logger.info(f"已创建输出目录: {output_dir}")
        except Exception as e:
            logger.error(f"创建输出目录失败: {str(e)}")
            return 1
    
    # 创建并启动事件监控器
    try:
        monitor = EventMonitor(
            test_mode=args.test_mode,
            output_path=args.output_path,
            sampling_rate=args.sampling_rate,
            encryption=args.encryption,
            filter_sensitive=args.filter_sensitive,
            buffer_size=args.buffer_size,
            flush_interval=args.flush_interval
        )
        
        if not monitor.start():
            logger.error("启动监控器失败")
            return 1
        
        # 打印状态信息
        mode = "测试" if args.test_mode else "正常"
        print(f"\n事件监控器已启动（{mode}模式）")
        print(f"输出文件: {args.output_path}")
        print(f"刷新间隔: {args.flush_interval}秒")
        print(f"采样率: {args.sampling_rate}")
        if args.encryption:
            print("输出文件已加密")
        print("按Ctrl+C停止...\n")
        
        # 保持程序运行，直到用户按下Ctrl+C
        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n接收到停止信号，正在停止监控器...")
        finally:
            # 停止监控器
            monitor.stop()
            print(f"已记录{monitor.event_count}个事件")
            print(f"数据已保存到: {args.output_path}")
        
        return 0
    except Exception as e:
        logger.error(f"运行过程中发生错误: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())