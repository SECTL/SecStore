import os
import sys
import json

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtNetwork import *
from qfluentwidgets import *
from loguru import logger

from app.common.config import cfg, VERSION
from app.view.SecStore import Window

def send_ipc_message():
    """(^・ω・^ ) 白露的IPC信使魔法！
    正在向已运行的实例发送唤醒消息～ 就像传递小纸条一样神奇！
    如果成功连接，会发送'show'指令或URL命令让窗口重新出现哦～ ✨"""
    socket = QLocalSocket()
    socket.connectToServer(IPC_SERVER_NAME)

    if socket.waitForConnected(1000):
        # 发送普通的show指令
        socket.write(b"show")
        logger.debug("IPC show消息发送成功～ ")
        socket.flush()
        socket.waitForBytesWritten(1000)
        socket.disconnectFromServer()
        return True
    logger.warning("IPC连接失败，目标实例可能未响应～ ")
    return False


def configure_logging():
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
        logger.info("日志文件夹创建成功～ ")

    logger.configure(patcher=lambda record: record)

    logger.add(
        os.path.join(log_dir, "SecStore_{time:YYYY-MM-DD}.log"),
        rotation="1 MB",
        encoding="utf-8",
        retention="30 days",
        format="{time:YYYY-MM-DD HH:mm:ss:SSS} | {level} | {name}:{function}:{line} - {message}",
        enqueue=True,  # 启用异步日志记录，像派出小信使一样高效
        compression="tar.gz", # 启用压缩魔法，节省存储空间～
        backtrace=True,  # 启用回溯信息，像魔法追踪器一样定位问题
        diagnose=True,  # 启用诊断信息，提供更详细的魔法检查报告
        catch=True  # 捕获未处理的异常，保护程序稳定运行～
    )
    logger.info("日志系统配置完成，可以开始记录冒险啦～ ")

if cfg.get(cfg.dpiScale) == "Auto":
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    logger.debug("DPI缩放已设置为自动模式～ ")
else:
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
    os.environ["QT_SCALE_FACTOR"] = str(cfg.get(cfg.dpiScale))
    logger.debug(f"DPI缩放已设置为{cfg.get(cfg.dpiScale)}倍～ ")

IPC_SERVER_NAME = 'SecStoreIPC'  # IPC通讯服务器名称
SHARED_MEMORY_KEY = 'SecStore'   # 共享内存密钥

app = QApplication(sys.argv)
logger.debug("QApplication实例已创建 ")


def check_single_instance():
    """(ﾟДﾟ≡ﾟдﾟ) 星野的单实例守卫启动！
    正在执行魔法结界检查，禁止多个程序副本同时运行喵！
    这是为了防止魔法冲突和资源争夺，保证程序稳定运行哦～ 🔒✨"""
    shared_memory = QSharedMemory(SHARED_MEMORY_KEY)
    if not shared_memory.create(1):
        logger.debug('检测到已有 SecStore 实例正在运行喵！')

        # 异步发送IPC消息，避免阻塞启动流程
        def async_wakeup():
            # 尝试直接发送IPC消息唤醒已有实例
            if send_ipc_message():
                logger.info('成功唤醒已有实例，当前实例将退出喵～')
                sys.exit()
            else:
                # IPC连接失败，短暂延迟后重试一次
                QTimer.singleShot(300, lambda:
                    retry_ipc() if not send_ipc_message() else None
                )

        def retry_ipc():
            logger.error("无法连接到已有实例，程序将退出喵～")
            sys.exit()

        # 立即异步执行唤醒操作
        QTimer.singleShot(0, async_wakeup)
        # 等待异步操作完成
        QApplication.processEvents()
        sys.exit()
    logger.info('单实例检查通过，可以安全启动程序喵～')
    return shared_memory

def initialize_application():
    logger.info("软件启动成功～ ")
    logger.info(f"软件作者: lzy98276")
    logger.info(f"软件Github地址: https://github.com/SECTL/SecStore")

    # 创建主窗口实例
    sec = Window()
    sec.show()
    logger.info("根据设置显示主窗口～ ")
    return sec

if __name__ == "__main__":
    # 配置日志系统
    configure_logging()
    
    # 检查单实例并创建共享内存
    shared_memory = check_single_instance()
    
    # 初始化应用程序并创建主窗口
    sec = initialize_application()

    # 启动应用程序事件循环
    try:
        logger.info("应用程序事件循环启动喵～")
        app.exec_()
    finally:
        shared_memory.detach()
        logger.info("共享内存已释放，程序完全退出喵～")
        sys.exit()