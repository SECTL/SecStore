from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtNetwork import *
from PyQt5.QtGui import *
from qfluentwidgets import *

import os
import sys
import json

from loguru import logger

from app.view.recommend import recommend_dialog
# from app.view.screen_annotation import screen_annotation_dialog
# from app.view.calendar import calendar_dialog
# from app.view.auxiliary_interface import auxiliary_interface_dialog
# from app.view.settings import settings_Window
# from app.view.about import about_Window

class Window(FluentWindow):
    def __init__(self):
        super().__init__()
        # 设置窗口属性
        window_width = 900
        window_height = 700
        self.resize(window_width, window_height)
        self.setMinimumSize(window_width, window_height)
        self.setWindowTitle('SecStore')
        self.setWindowIcon(QIcon('./app/resource/icon/SecStore.png'))

        # # 检查更新
        # check_startup = self.config_manager.get_foundation_setting('check_on_startup')
        # if check_startup:
        #     self.check_updates_async()

        # 创建子界面
        self.createSubInterface()

        # 显示主窗口
        self.show()
        logger.info("白露魔法: 根据设置自动显示主窗口～ ")

    def createSubInterface(self):
        """(^・ω・^ ) 白露的魔法建筑师开工啦！
        正在搭建子界面导航系统，就像建造一座功能齐全的魔法城堡～
        每个功能模块都是城堡的房间，马上就能入住使用啦！🏰✨"""
        # 创建推荐界面
        self.recommendInterface = recommend_dialog(self)
        self.recommendInterface.setObjectName("recommendInterface")
        logger.debug("推荐界面房间已建成 ")

        # # 创建屏幕批注与白板软件界面
        # self.screen_annotationInterface = screen_annotation_dialog(self)
        # self.screen_annotationInterface.setObjectName("screen_annotationInterface")
        # logger.debug("屏幕批注与白板软件界面房间已建成 ")

        # # 创建课表与看板类软件界面
        # self.calendarInterface = calendar_dialog(self)
        # self.calendarInterface.setObjectName("calendarInterface")
        # logger.debug("课表与看板类软件界面房间已建成 ")

        # # 创建辅助类软件与实用工具界面
        # self.auxiliary_interface = auxiliary_interface_dialog(self)
        # self.auxiliary_interface.setObjectName("auxiliary_interface")
        # logger.debug("辅助类软件与实用工具界面房间已建成 ")


        # # 创建设置界面
        # self.settingInterface = settings_Window(self)
        # self.settingInterface.setObjectName("settingInterface")
        # logger.debug("设置界面房间已建成 ")

        # # 创建关于界面
        # self.about_settingInterface = about_Window(self)
        # self.about_settingInterface.setObjectName("about_settingInterface")
        # logger.debug("关于界面房间已建成 ")

        # 初始化导航系统
        self.initNavigation()
        logger.info("所有子界面和导航系统已完工！")

    def initNavigation(self):
        self.addSubInterface(self.recommendInterface, FluentIcon.HOME, '推荐', position=NavigationItemPosition.TOP)
        # self.addSubInterface(self.screen_annotationInterface, FluentIcon.PENCIL_INK, '屏幕批注与白板软件', position=NavigationItemPosition.TOP)
        # self.addSubInterface(self.calendarInterface, FluentIcon.CALENDAR, '课表与看板类软件', position=NavigationItemPosition.TOP)
        # self.addSubInterface(self.auxiliary_interface, FluentIcon.DEVELOPER_TOOLS, '辅助类软件与实用工具', position=NavigationItemPosition.TOP)

        # self.addSubInterface(self.settingInterface, FluentIcon.SETTING, '设置', position=NavigationItemPosition.BOTTOM)
        # self.addSubInterface(self.about_settingInterface, FluentIcon.INFO, '关于', position=NavigationItemPosition.BOTTOM)
        
        logger.info("所有导航项已布置完成，导航系统可以正常使用啦～ ")

    # def closeEvent(self, event):
    #     self.hide()
    #     event.ignore()
    #     logger.info("窗口关闭事件已拦截，程序已转入后台运行～ ")
