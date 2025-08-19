from qfluentwidgets import * 
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtNetwork import *

import json
import os
from loguru import logger

from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from packaging.version import Version
import comtypes
from comtypes import POINTER

# 默认更新通道配置文件路径
CHANNEL_CONFIG_PATH = './app/Settings/Settings.json'

def get_update_channel():
    """获取当前选择的更新通道，默认为稳定通道"""
    try:
        if os.path.exists(CHANNEL_CONFIG_PATH):
            with open(CHANNEL_CONFIG_PATH, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config.get('channel', 'stable')
        return 'stable'
    except Exception as e:
        logger.error(f"读取更新通道配置失败: {e}")
        return 'stable'

def set_update_channel(channel):
    """保存更新通道配置，保留其他配置信息"""
    try:
        # 读取现有配置
        config = {}
        if os.path.exists(CHANNEL_CONFIG_PATH):
            with open(CHANNEL_CONFIG_PATH, 'r', encoding='utf-8') as f:
                config = json.load(f)
        
        # 更新通道配置
        config['channel'] = channel
        
        # 保存更新后的配置
        with open(CHANNEL_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        logger.info(f"更新通道已设置为: {channel}")
    except json.JSONDecodeError:
        logger.error("配置文件格式错误，将创建新的配置文件")
        # 创建新的配置文件
        with open(CHANNEL_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump({'channel': channel}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存更新通道配置失败: {e}")


def check_for_updates(channel=None):
    """(^・ω・^ ) 白露的更新检查魔法！
    偷偷摸摸在后台检查更新，不会打扰到用户哦～ ✨
    支持稳定通道(stable)和测试通道(beta)，就像有两个不同的魔法口袋！"""
    # 如果未指定通道，使用配置中的默认通道
    if channel is None:
        channel = get_update_channel()
    try:
        current_version = VERSION.lstrip('v')
        if channel == 'stable':
            url = "https://api.github.com/repos/SECTL/SecStore/releases/latest"
        else:
            url = "https://api.github.com/repos/SECTL/SecStore/releases"

        # (ﾟДﾟ≡ﾟдﾟ) 星野的Qt网络请求魔法！
        network_manager = QNetworkAccessManager()
        event_loop = QEventLoop()
        
        request = QNetworkRequest(QUrl(url))
        request.setRawHeader(b'User-Agent', b'SecStore-Updater')
        
        reply = network_manager.get(request)
        reply.finished.connect(event_loop.quit)
        
        # 等待请求完成
        event_loop.exec_()
        
        if reply.error() != QNetworkReply.NoError:
            logger.error(f"(×﹏×) 白露出错: 网络请求失败了呢～ {reply.errorString()}")
            return False, None
            
        response_data = reply.readAll().data().decode('utf-8')
        response_json = json.loads(response_data)
        
        if channel == 'stable':
            latest_release = response_json
            latest_version_tag = latest_release['tag_name']
        else:
            # 获取所有发布并筛选预发布版本
            releases = response_json
            # 解析所有版本并比较版本号
            all_versions = []
            for release in releases:
                version_tag = release['tag_name']
                # 提取版本号并移除'v'前缀
                version = version_tag.lstrip('v')
                all_versions.append((Version(version), release))
            # 按版本号降序排序
            all_versions.sort(reverse=True, key=lambda x: x[0])
            if not all_versions:
                return False, None
            latest_version, latest_release = all_versions[0]
            latest_version_tag = latest_release['tag_name']

        latest_version = latest_version_tag.lstrip('v')
        if Version(latest_version) > Version(current_version):
            logger.info(f"当前版本 {current_version}, 最新版本 {latest_version_tag}，准备通知用户")
            return True, latest_version_tag
        else:
            logger.info(f"当前版本 {current_version} 已经是最新的啦，不需要更新")
            return False, None
    except json.JSONDecodeError as e:
        logger.error(f"API响应格式不对哦 {e}")
        return False, None
    except Exception as e:
        logger.error(f"检查更新失败了 {e}")
        return False, None

def load_custom_font():
    font_path = './app/resource/font/HarmonyOS_Sans_SC_Bold.ttf'
    font_id = QFontDatabase.addApplicationFont(font_path)
    if font_id < 0:
        logger.error(f"加载自定义字体失败: {font_path}")
        return None
    font_family = QFontDatabase.applicationFontFamilies(font_id)[0]
    return font_family

def is_dark_theme(qconfig):
    if qconfig.theme == Theme.AUTO:
        lightness = QApplication.palette().color(QPalette.Window).lightness()
        return lightness <= 127
    else:
        return qconfig.theme == Theme.DARK

class Config(QConfig):
    dpiScale = OptionsConfigItem(
        "Window", "DpiScale", "Auto", OptionsValidator([1, 1.25, 1.5, 1.75, 2, "Auto"]), restart=True)

YEAR = 2025
MONTH = 4
AUTHOR = "lzy98276"
VERSION = "v0.0.0.0"
APPLY_NAME = "SecStore"
GITHUB_WEB = "https://github.com/SECTL/SecStore"
BILIBILI_WEB = "https://space.bilibili.com/520571577"

cfg = Config()

cfg.themeMode.value = Theme.AUTO
qconfig.load('./app/Settings/config.json', cfg)