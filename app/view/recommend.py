from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtNetwork import *
from PyQt5.QtGui import *
from PyQt5.Qt import *
from qfluentwidgets import *

import os
import sys
import json
import sip
import functools
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.packages.urllib3.exceptions import InsecureRequestWarning

# 禁用SSL验证警告
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
# 禁用所有SSL相关警告
import warnings
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

from loguru import logger
from app.common.config import load_custom_font, is_dark_theme

class recommend_dialog(QWidget):
    """应用商店推荐页面"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("recommend_dialog")
        
        # 初始化数据
        self.all_apps = []
        self.app_cards = []  # 存储所有卡片
        self.recommend_container = None  # 推荐容器
        self._last_width = 0  # 记录上次窗口宽度
        self._last_max_cards_per_row = 0  # 记录上次每行卡片数量
        self._is_fetching = False  # 防止重复请求标志
        self._retry_count = 0  # 重试计数器
        self._loaded_cards_count = 0  # 已加载的卡片计数
        self._total_cards_count = 0  # 总卡片数
        self._mutex = QMutex()  # 线程同步锁
        self.cards_layout = None  # 卡片布局
        self.scroll_area = None  # 滚动区域
        self._init_completed = False  # 初始化完成标志
        self.search_box = None  # 搜索框
        self.current_search_text = ""  # 当前搜索文本
        self.filtered_apps = []  # 过滤后的应用列表
        self._last_search_text = ""  # 上次搜索文本，用于检测清除操作
        self._last_layout_time = 0  # 上次布局时间，用于防抖机制
        self._is_clearing = False  # 清除操作进行中标志，防止重复触发
        self._clear_timer = None  # 清除操作防抖定时器
        self._search_timer = None  # 搜索防抖定时器
        
        # 初始化网络管理器
        self.network_manager = QNetworkAccessManager()
        # 不再全局连接finished信号，而是为每个请求单独处理
        
        # 初始化UI
        self.init_ui()
        
        # UI初始化完成后获取软件列表
        QTimer.singleShot(100, self.fetch_software_list)
        
    def init_ui(self):
        """初始化用户界面"""
        # 创建主滚动区域
        self.main_scroll_area = SingleDirectionScrollArea(orient=Qt.Vertical)
        self.main_scroll_area.setObjectName("main_scroll_area")
        self.main_scroll_area.setWidgetResizable(True)
        
        # 创建主内容容器
        self.main_content_widget = QWidget()
        self.main_content_widget.setObjectName("main_content_widget")
        self.main_content_layout = QVBoxLayout(self.main_content_widget)
        self.main_content_layout.setContentsMargins(0, 0, 0, 0)
        self.main_content_layout.setAlignment(Qt.AlignTop | Qt.AlignVCenter | Qt.AlignHCenter)
        
        # 设置主滚动区域的内容
        self.main_scroll_area.setWidget(self.main_content_widget)
        
        # 设置滚动区域样式为透明背景
        self.main_scroll_area.setStyleSheet("QScrollArea{background: transparent; border: none}")
        self.main_content_widget.setStyleSheet("QWidget{background: transparent}")
        
        # 主布局
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.addWidget(self.main_scroll_area)
        
        # 创建搜索框
        self.create_search_box()

        # 创建顶部FlipView轮播图
        self.create_flip_view()
        
        # 创建推荐软件卡片
        self.create_recommend_cards()
        
    def create_flip_view(self):
        """创建顶部轮播图"""
        # 创建容器widget来包裹flipView，用于设置边距
        container = QWidget()
        container.setObjectName("carousel_container")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(20, 20, 20, 20)  # 上20，左20，下20，右20
        # 设置容器布局垂直居上对齐
        container_layout.setAlignment(Qt.AlignTop | Qt.AlignCenter)

        flipView = HorizontalFlipView()
        flipView.setObjectName("carousel_flipview")
        flipView.addImages(["app/resource/assets/carousel/ClassIsland.png", "app/resource/assets/carousel/Class_Widgets.png"])
        flipView.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        flipView.setFixedSize(QSize(800, 400))
        # 设置轮播图项之间的间距
        flipView.setSpacing(20)

        container_layout.addWidget(flipView)
        # 添加拉伸因子，确保容器不会占据多余空间
        self.main_content_layout.addWidget(container, alignment=Qt.AlignTop | Qt.AlignHCenter)
        
        # 保存轮播图容器引用
        self.carousel_container = container
        
    def create_search_box(self):
        """创建搜索框"""
        # 创建搜索框容器
        search_container = QWidget()
        search_container.setObjectName("search_container")
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(20, 10, 20, 10)
        search_layout.setAlignment(Qt.AlignCenter)
        
        # 创建搜索框
        self.search_box = SearchLineEdit()
        self.search_box.setObjectName("search_box")
        self.search_box.setPlaceholderText("搜索软件名称、简介或分类...")
        self.search_box.setFixedSize(600, 40)
        self.search_box.setClearButtonEnabled(True)
        
        # 连接搜索信号
        self.search_box.textChanged.connect(self.on_search_text_changed)
        self.search_box.returnPressed.connect(self.on_search_pressed)
        # 连接清除按钮信号，处理搜索框清空情况
        if hasattr(self.search_box, 'clearButtonClicked'):
            self.search_box.clearButtonClicked.connect(self.on_search_cleared)
        else:
            # 如果没有clearButtonClicked信号，使用textChanged信号来检测清除操作
            # 确保清除检测信号总是被连接
            try:
                self.search_box.textChanged.connect(self._on_text_changed_for_clear)
            except Exception as e:
                logger.warning(f"无法连接清除检测信号: {e}")
        
        # 添加到布局
        search_layout.addWidget(self.search_box)
        search_layout.addStretch()
        
        # 添加到主布局
        self.main_content_layout.addWidget(search_container)
        
    def create_recommend_cards(self):
        """创建推荐软件卡片"""
        # 创建推荐软件容器
        self.recommend_container = QWidget()
        self.recommend_container.setObjectName("recommend_container")
        recommend_layout = QVBoxLayout(self.recommend_container)
        recommend_layout.setContentsMargins(20, 20, 20, 20)
        recommend_layout.setSpacing(20)
        recommend_layout.setAlignment(Qt.AlignLeft)
        
        # 添加"推荐软件"标题
        title_label = TitleLabel("推荐软件")
        title_label.setObjectName("recommend_title")
        title_label.setAlignment(Qt.AlignLeft)
        recommend_layout.addWidget(title_label)
        
        # 保存推荐标题引用
        self.recommend_title = title_label
        
        # 创建三个固定分类标签区域
        categories = [
            "屏幕批注与白板软件",
            "课表与看板类软件", 
            "辅助类软件与实用工具"
        ]
        
        # 为每个分类创建容器和标题
        self.category_widgets = {}
        self.category_cards_widgets = {}
        
        for category in categories:
            # 创建分类容器
            category_widget = QWidget()
            category_widget.setObjectName(f"category_{category}")
            category_layout = QVBoxLayout(category_widget)
            category_layout.setContentsMargins(0, 10, 0, 10)
            category_layout.setSpacing(15)
            category_layout.setAlignment(Qt.AlignLeft)
            
            # 创建分类标题
            category_title = TitleLabel(category)
            category_title.setObjectName(f"category_title_{category}")
            category_title.setAlignment(Qt.AlignLeft)
            category_layout.addWidget(category_title)
            
            # 创建该分类的卡片容器
            cards_widget = QWidget()
            cards_widget.setObjectName(f"cards_widget_{category}")
            # 不在这里创建布局，在layout_cards方法中统一创建
            
            category_layout.addWidget(cards_widget)
            recommend_layout.addWidget(category_widget)
            
            # 保存引用
            self.category_widgets[category] = category_widget
            self.category_cards_widgets[category] = cards_widget
        
        # 设置滚动区域引用
        self.scroll_area = self.main_scroll_area
        
        # 初始化卡片列表
        self.app_cards = []
        
        # 初始化分类卡片映射
        self.category_cards = {
            "屏幕批注与白板软件": [],
            "课表与看板类软件": [],
            "辅助类软件与实用工具": []
        }
        
        # 添加到主布局
        self.main_content_layout.addWidget(self.recommend_container)
        # 注意：初始布局将在数据加载完成后自动调用，避免重复布局

    def layout_cards(self, force_refresh=False):
        """动态布局卡片，根据窗口宽度自动调整每行显示的卡片数量"""
        # 防抖机制：避免短时间内重复调用
        current_time = QDateTime.currentMSecsSinceEpoch()
        if hasattr(self, '_last_layout_time') and not force_refresh:
            if current_time - self._last_layout_time < 200:  # 200ms内不重复布局
                return
        self._last_layout_time = current_time
        
        # 计算每行应该显示的卡片数量
        container_width = self.width() - 40  # 减去左右边距
        card_width = 350
        card_spacing = 15
        
        # 计算每行最多能显示的卡片数量
        max_cards_per_row = max(1, int((container_width + card_spacing) / (card_width + card_spacing)))
        
        # 检查布局是否真的需要改变
        if hasattr(self, '_last_max_cards_per_row') and not force_refresh:
            if self._last_max_cards_per_row == max_cards_per_row:
                return  # 布局没有变化，不需要重排
        self._last_max_cards_per_row = max_cards_per_row
        
        # 设置窗口不更新，减少闪烁
        self.setUpdatesEnabled(False)
        
        try:
            # 为每个分类单独布局卡片
            for category, cards in self.category_cards.items():
                if category not in self.category_cards_widgets:
                    continue
                    
                cards_widget = self.category_cards_widgets[category]
                
                # 完全重建widget以避免布局冲突
                # 保存当前widget的父布局和位置信息
                parent_layout = cards_widget.parent().layout() if cards_widget.parent() else None
                layout_index = -1
                if parent_layout:
                    for i in range(parent_layout.count()):
                        if parent_layout.itemAt(i).widget() == cards_widget:
                            layout_index = i
                            break
                
                # 从父布局中移除当前widget
                if parent_layout and layout_index >= 0:
                    parent_layout.takeAt(layout_index)
                
                # 创建新的widget来替换旧的
                new_cards_widget = QWidget()
                new_cards_widget.setObjectName(f"cards_widget_{category}")
                new_cards_widget.setSizePolicy(cards_widget.sizePolicy())
                
                # 将新widget添加到父布局中的原位置
                if parent_layout and layout_index >= 0:
                    parent_layout.insertWidget(layout_index, new_cards_widget)
                
                # 更新引用
                self.category_cards_widgets[category] = new_cards_widget
                cards_widget = new_cards_widget
                
                # 彻底删除旧的widget及其所有子部件
                old_widget = cards_widget
                if old_widget != new_cards_widget:
                    old_widget.setParent(None)
                    old_widget.deleteLater()
                
                # 等待Qt完全处理widget删除
                QApplication.processEvents()
                import time
                time.sleep(0.05)  # 50ms同步等待
                QApplication.processEvents()
                
                # 创建新的布局
                category_layout = QVBoxLayout(cards_widget)
                category_layout.setContentsMargins(0, 0, 0, 0)
                category_layout.setSpacing(20)
                category_layout.setAlignment(Qt.AlignHCenter)
                
                # 检查是否处于搜索状态
                is_searching = hasattr(self, 'current_search_text') and self.current_search_text
                
                # 搜索状态下，隐藏没有匹配应用的分类
                if is_searching and not cards:
                    # 隐藏该分类的widget
                    if category in self.category_widgets:
                        self.category_widgets[category].hide()
                    continue
                
                # 确保分类可见（搜索状态有卡片，或非搜索状态）
                if category in self.category_widgets:
                    self.category_widgets[category].show()
                
                # 如果该分类没有卡片
                if not cards:
                    if is_searching:
                        # 搜索状态下，只在第一个分类显示统一的空状态提示
                        categories = list(self.category_cards_widgets.keys())
                        if category == categories[0]:
                            empty_label = BodyLabel(f"未找到包含 '{self.current_search_text}' 的应用")
                            empty_label.setObjectName("empty_label_search")
                            empty_label.setAlignment(Qt.AlignCenter)
                            empty_label.setFont(QFont(load_custom_font(), 12))
                            empty_label.setStyleSheet("color: #666;")
                            category_layout.addWidget(empty_label)
                        # 其他没有匹配的分类已经在上面的逻辑中隐藏了
                    else:
                        # 非搜索状态，每个分类显示各自的空状态
                        empty_label = BodyLabel("暂无应用")
                        empty_label.setObjectName(f"empty_label_{category}")
                        empty_label.setAlignment(Qt.AlignCenter)
                        empty_label.setFont(QFont(load_custom_font(), 10))
                        category_layout.addWidget(empty_label)
                    continue
                
                # 创建当前行容器
                current_row = QWidget()
                current_row.setObjectName(f"cards_row_{category}")
                row_layout = QHBoxLayout(current_row)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(card_spacing)
                row_layout.setAlignment(Qt.AlignHCenter)
                
                # 动态布局该分类的卡片
                for i, card in enumerate(cards):
                    # 如果当前行已满，创建新行
                    if i > 0 and i % max_cards_per_row == 0:
                        # 添加两侧拉伸因子，使卡片居中对齐
                        row_layout.addStretch(1)
                        row_layout.insertStretch(0, 1)
                        # 将当前行添加到内容容器
                        category_layout.addWidget(current_row)
                        
                        # 创建新的一行
                        current_row = QWidget()
                        current_row.setObjectName(f"cards_row_{category}_{i}")
                        row_layout = QHBoxLayout(current_row)
                        row_layout.setContentsMargins(0, 0, 0, 0)
                        row_layout.setSpacing(card_spacing)
                        row_layout.setAlignment(Qt.AlignHCenter)
                    
                    # 将卡片添加到当前行
                    row_layout.addWidget(card)
                
                # 添加最后一行的拉伸因子和布局，使卡片居中对齐
                row_layout.addStretch(1)
                row_layout.insertStretch(0, 1)
                category_layout.addWidget(current_row)
        
        finally:
            # 恢复窗口更新
            self.setUpdatesEnabled(True)
            # 强制重绘
            self.update()
            
    def on_search_text_changed(self, text):
        """搜索框文本变化时的处理"""
        # 额外的清除检测保护机制 - 确保任何情况下清空都能触发刷新
        if not text.strip() and hasattr(self, '_last_search_text') and self._last_search_text.strip():
            logger.debug("on_search_text_changed检测到清除操作，强制刷新")
            # 停止可能存在的搜索定时器
            if hasattr(self, '_search_timer') and self._search_timer:
                self._search_timer.stop()
            # 延迟触发清除，确保用户完成删除操作
            if hasattr(self, '_clear_timer') and self._clear_timer:
                self._clear_timer.stop()
            
            self._clear_timer = QTimer()
            self._clear_timer.setSingleShot(True)
            self._clear_timer.timeout.connect(self.on_search_cleared)
            self._clear_timer.start(100)  # 100ms防抖延迟
            return
            
        # 注意：空文本的处理现在由_on_text_changed_for_clear方法负责
        # 这里只处理非空文本的搜索延迟
        if text.strip():
            # 停止可能存在的清除定时器
            if hasattr(self, '_clear_timer') and self._clear_timer:
                self._clear_timer.stop()
            
            # 使用定时器延迟搜索，避免频繁搜索
            if hasattr(self, '_search_timer') and self._search_timer:
                self._search_timer.stop()
            
            self._search_timer = QTimer()
            self._search_timer.setSingleShot(True)
            self._search_timer.timeout.connect(lambda: self.perform_search(text))
            self._search_timer.start(300)  # 300ms延迟
        
    def on_search_pressed(self):
        """搜索框按下回车时的处理"""
        text = self.search_box.text()
        self.perform_search(text)
        
    def _on_text_changed_for_clear(self, text):
        """文本变化时的清除检测，用于处理没有clearButtonClicked信号的情况"""
        # 检查是否从有文本变为无文本（更敏感的检测）
        if hasattr(self, '_last_search_text'):
            # 检查上一次是否有文本内容（去除空格后不为空）
            had_content = bool(self._last_search_text and self._last_search_text.strip())
            # 检查当前是否没有内容（去除空格后为空）
            no_content = not text.strip()
            
            # 如果从有内容变为无文本，触发清除操作
            if had_content and no_content:
                # 检查是否已经在处理清除操作，避免重复触发
                if hasattr(self, '_is_clearing') and self._is_clearing:
                    logger.debug("清除操作已在处理中，跳过重复触发")
                    return
                
                # 添加额外的防抖延迟，确保用户完成删除操作
                if hasattr(self, '_clear_timer'):
                    self._clear_timer.stop()
                
                self._clear_timer = QTimer()
                self._clear_timer.setSingleShot(True)
                self._clear_timer.timeout.connect(self.on_search_cleared)
                self._clear_timer.start(100)  # 100ms防抖延迟
                
                logger.debug("检测到搜索框清空操作，延迟触发刷新")
        
        # 更新最后文本记录
        self._last_search_text = text
        
    def on_search_cleared(self):
        """搜索框清除按钮点击时的处理"""
        # 检查是否已经在处理清除操作，避免重复触发
        if hasattr(self, '_is_clearing') and self._is_clearing:
            logger.debug("清除操作已在处理中，跳过重复触发")
            return
            
        logger.debug("搜索框清除操作触发，强制刷新显示所有应用")
        # 设置清除标志，防止重复处理
        self._is_clearing = True
        
        try:
            # 重置搜索状态
            self.current_search_text = ""
            # 清空搜索框文本
            if hasattr(self, 'search_box'):
                self.search_box.setText("")
            # 当搜索框被清空时，强制刷新显示所有应用
            self.show_all_apps()
        finally:
            # 确保在任何情况下都重置标志
            self._is_clearing = False
        
    def hide_search_ui_elements(self):
        """隐藏轮播图和分类标题，只显示搜索结果"""
        # 隐藏轮播图容器
        if hasattr(self, 'carousel_container'):
            self.carousel_container.hide()
        
        # 隐藏分类标题
        for category, category_widget in self.category_widgets.items():
            if category_widget:
                # 查找分类标题并隐藏
                for child in category_widget.children():
                    if isinstance(child, TitleLabel) and child.objectName().startswith('category_title_'):
                        child.hide()
        
        # 隐藏推荐软件标题
        if hasattr(self, 'recommend_title'):
            self.recommend_title.hide()
            
    def show_search_ui_elements(self):
        """重新显示轮播图和分类标题"""
        # 显示轮播图容器
        if hasattr(self, 'carousel_container'):
            self.carousel_container.show()
        
        # 显示分类标题
        for category, category_widget in self.category_widgets.items():
            if category_widget:
                # 查找分类标题并显示
                for child in category_widget.children():
                    if isinstance(child, TitleLabel) and child.objectName().startswith('category_title_'):
                        child.show()
        
        # 显示推荐软件标题
        if hasattr(self, 'recommend_title'):
            self.recommend_title.show()
        
    def perform_search(self, search_text):
        """执行搜索操作"""
        self.current_search_text = search_text.strip()
        
        if not self.current_search_text:
            # 搜索框为空，显示所有应用
            logger.debug("搜索框为空，显示所有应用")
            self.show_all_apps()
            return
        
        # 执行搜索过滤
        self.filtered_apps = []
        search_text_lower = self.current_search_text.lower()
        
        # 遍历所有应用进行匹配
        for app_data in self.all_apps:
            # 检查软件名称
            name_match = search_text_lower in app_data['name'].lower()
            
            # 检查软件简介
            desc_match = search_text_lower in app_data['description'].lower()
            
            # 检查软件分类
            category_match = search_text_lower in app_data['category'].lower()
            
            # 如果任一条件匹配，则添加到过滤结果
            if name_match or desc_match or category_match:
                self.filtered_apps.append(app_data)
        
        # 隐藏轮播图和分类标题，只显示搜索结果
        self.hide_search_ui_elements()
        
        # 更新显示，强制刷新以确保搜索结果正确显示
        self.update_filtered_display(force_refresh=True)
        
    def show_all_apps(self):
        """显示所有应用"""
        logger.debug("开始显示所有应用，强制刷新")
        # 重置搜索状态
        self.current_search_text = ""
        # 重置过滤应用列表为所有应用
        self.filtered_apps = self.all_apps.copy()
        # 重新显示轮播图和分类标题
        self.show_search_ui_elements()
        
        # 完全重置布局状态，确保清除搜索时正确显示
        # 重置分类卡片映射
        self.category_cards = {
            "屏幕批注与白板软件": [],
            "课表与看板类软件": [],
            "辅助类软件与实用工具": []
        }
        
        # 重新分配应用到各个分类
        for app_data in self.all_apps:
            category = app_data.get('category', '辅助类软件与实用工具')
            if category in self.category_cards:
                self.category_cards[category].append(app_data)
        
        # 强制刷新显示所有应用，确保完全重绘
        self.update_filtered_display(force_refresh=True)
        logger.debug("完成所有应用的显示刷新")
        
    def update_filtered_display(self, force_refresh=False):
        """更新过滤后的显示"""
        # 清空现有卡片
        for card in self.app_cards:
            card.deleteLater()
        self.app_cards.clear()
        
        # 清空分类卡片
        for category in self.category_cards:
            self.category_cards[category].clear()
        
        # 检查是否在搜索状态
        is_searching = hasattr(self, 'search_box') and self.search_box.text().strip()
        
        # 如果没有过滤结果，显示提示
        if not self.filtered_apps:
            # 只在搜索状态下显示无结果提示
            if is_searching:
                self.show_no_results_message()
            else:
                # 非搜索状态，正常显示空分类
                self.layout_cards(force_refresh=force_refresh)
            return
        
        # 重新创建过滤后的卡片
        for app_data in self.filtered_apps:
            card = self.create_app_card(
                app_data['name'],
                app_data['category'],
                app_data['description'],
                app_data['icon'],
                app_data['stars'],
                app_data['downloads'],
                app_data.get('banner', ''),
                app_data.get('repo_name')
            )
            
            if card:
                # 根据软件类型确定分类
                category = self._get_category_by_app_type(app_data['category'])
                
                # 将卡片添加到对应的分类中
                self.app_cards.append(card)
                self.category_cards[category].append(card)
        
        # 重新布局卡片，强制刷新以确保正确显示
        self.layout_cards(force_refresh=force_refresh)
        
    def show_no_results_message(self):
        """显示无搜索结果消息"""
        # 确保在显示无结果消息时也隐藏轮播图和分类标题
        self.hide_search_ui_elements()
        
        # 调用layout_cards来处理空状态显示，现在空状态逻辑已在layout_cards中统一处理
        self.layout_cards(force_refresh=True)
    
    def resizeEvent(self, event):
        """窗口大小变化时重新布局卡片"""
        super().resizeEvent(event)
        # 检查窗口宽度是否真的发生了变化，避免不必要的重布局
        if hasattr(self, '_last_width'):
            if abs(self.width() - self._last_width) < 50:  # 宽度变化小于50像素时不重布局
                return
        self._last_width = self.width()
        
        # 更新滚动区域大小
        if hasattr(self, 'scroll_area'):
            # 根据窗口高度动态调整滚动区域高度
            available_height = self.height() - 350  # 减去轮播图和其他元素的高度
            if available_height > 300:
                self.scroll_area.setMinimumHeight(min(available_height, 600))
        
        # 延迟重新布局，避免频繁调用，使用强制刷新确保正确显示
        QTimer.singleShot(200, lambda: self.layout_cards(force_refresh=True))
        
    def validate_and_fix_repo_name(self, repo_name, url=None):
        """验证并修正仓库名格式，从url中获取正确的组织信息"""
        if not repo_name:
            return None
            
        # 如果仓库名格式正确（包含/），直接返回
        if '/' in repo_name:
            return repo_name
            
        # 如果仓库名不包含/，尝试从url中提取组织信息
        if url and 'github.com' in url:
            try:
                # 从GitHub URL中提取用户名/组织名和仓库名
                if '/blob/' in url:
                    # 处理blob URL: github.com/username/repo/blob/branch/path
                    url_parts = url.split('github.com/')[1].split('/')
                    if len(url_parts) >= 2:
                        username = url_parts[0]
                        repo_name_from_url = url_parts[1]
                        return f"{username}/{repo_name_from_url}"
                else:
                    # 处理其他GitHub URL格式
                    url_parts = url.split('github.com/')[1].split('/')
                    if len(url_parts) >= 2:
                        return f"{url_parts[0]}/{url_parts[1]}"
            except Exception as e:
                logger.warning(f"从URL提取仓库名失败: {e}")
        
        logger.warning(f"无法确定仓库名的正确格式: {repo_name}")
        return None
    
    def fetch_github_stars(self, repo_name, url=None):
        """从GitHub API获取仓库的stars数量"""
        # 验证并修正仓库名格式
        validated_repo_name = self.validate_and_fix_repo_name(repo_name, url)
        if not validated_repo_name:
            logger.warning(f"仓库名格式不正确且无法修正: {repo_name}，跳过获取stars")
            return 0
            
        try:
            # 构建GitHub API URL
            api_url = f"https://api.github.com/repos/{validated_repo_name}"
            request = QNetworkRequest(QUrl(api_url))
            request.setRawHeader(b"User-Agent", b"SecStore/1.0")
            
            # 创建事件循环等待API响应
            event_loop = QEventLoop()
            reply = self.network_manager.get(request)
            reply.finished.connect(event_loop.quit)
            
            # 等待请求完成
            event_loop.exec_()
            
            if reply.error() == QNetworkReply.NoError:
                response_data = reply.readAll().data().decode('utf-8')
                repo_info = json.loads(response_data)
                stars = repo_info.get('stargazers_count', 0)
                logger.info(f"成功获取仓库 {validated_repo_name} 的stars数量: {stars}")
                return stars
            else:
                logger.error(f"获取GitHub仓库stars失败 {validated_repo_name}: {reply.errorString()}")
                return 0
        except Exception as e:
            logger.error(f"获取GitHub仓库stars异常 {validated_repo_name}: {str(e)}")
            return 0
        finally:
            if 'reply' in locals():
                reply.deleteLater()
    
    def fetch_github_downloads(self, repo_name, url=None):
        """从GitHub API获取仓库的下载总量（通过所有release的下载量计算）"""
        # 验证并修正仓库名格式
        validated_repo_name = self.validate_and_fix_repo_name(repo_name, url)
        if not validated_repo_name:
            logger.warning(f"仓库名格式不正确且无法修正: {repo_name}，跳过获取下载量")
            return 0
            
        try:
            # 构建GitHub releases API URL
            api_url = f"https://api.github.com/repos/{validated_repo_name}/releases"
            request = QNetworkRequest(QUrl(api_url))
            request.setRawHeader(b"User-Agent", b"SecStore/1.0")
            
            # 创建事件循环等待API响应
            event_loop = QEventLoop()
            reply = self.network_manager.get(request)
            reply.finished.connect(event_loop.quit)
            
            # 等待请求完成
            event_loop.exec_()
            
            if reply.error() == QNetworkReply.NoError:
                response_data = reply.readAll().data().decode('utf-8')
                releases = json.loads(response_data)
                
                total_downloads = 0
                for release in releases:
                    # 累计所有assets的下载量
                    for asset in release.get('assets', []):
                        download_count = asset.get('download_count', 0)
                        total_downloads += download_count
                
                logger.info(f"成功获取仓库 {validated_repo_name} 的下载总量: {total_downloads}")
                return total_downloads
            else:
                logger.error(f"获取GitHub仓库下载量失败 {validated_repo_name}: {reply.errorString()}")
                return 0
        except Exception as e:
            logger.error(f"获取GitHub仓库下载量异常 {validated_repo_name}: {str(e)}")
            return 0
        finally:
            if 'reply' in locals():
                reply.deleteLater()
    
    def _fetch_github_stars_threaded(self, repo_name, url=None):
        """多线程版本：从GitHub API获取仓库的stars数量"""
        # 验证并修正仓库名格式
        validated_repo_name = self.validate_and_fix_repo_name(repo_name, url)
        if not validated_repo_name:
            logger.warning(f"仓库名格式不正确且无法修正: {repo_name}，跳过获取stars")
            return 0
            
        try:
            # 构建GitHub API URL
            api_url = f"https://api.github.com/repos/{validated_repo_name}"
            headers = {
                "User-Agent": "SecStore/1.0",
                "Accept": "application/vnd.github.v3+json"
            }
            
            # 使用requests发送请求，优化超时设置
            response = requests.get(api_url, headers=headers, timeout=(5, 10), verify=False)  # 连接超时5秒，读取超时10秒
            response.raise_for_status()
            
            repo_info = response.json()
            stars = repo_info.get('stargazers_count', 0)
            logger.info(f"成功获取仓库 {validated_repo_name} 的stars数量: {stars}")
            return stars
        except requests.exceptions.Timeout:
            logger.warning(f"获取GitHub仓库stars超时 {validated_repo_name}")
            return 0
        except requests.exceptions.RequestException as e:
            logger.error(f"获取GitHub仓库stars失败 {validated_repo_name}: {str(e)}")
            return 0
        except Exception as e:
            logger.error(f"获取GitHub仓库stars异常 {validated_repo_name}: {str(e)}")
            return 0
    
    def _fetch_github_downloads_threaded(self, repo_name, url=None):
        """多线程版本：从GitHub API获取仓库的下载总量"""
        # 验证并修正仓库名格式
        validated_repo_name = self.validate_and_fix_repo_name(repo_name, url)
        if not validated_repo_name:
            logger.warning(f"仓库名格式不正确且无法修正: {repo_name}，跳过获取下载量")
            return 0
            
        try:
            # 构建GitHub releases API URL
            api_url = f"https://api.github.com/repos/{validated_repo_name}/releases"
            headers = {
                "User-Agent": "SecStore/1.0",
                "Accept": "application/vnd.github.v3+json"
            }
            
            # 使用requests发送请求，优化超时设置
            response = requests.get(api_url, headers=headers, timeout=(5, 15), verify=False)  # 连接超时5秒，读取超时15秒
            response.raise_for_status()
            
            releases = response.json()
            total_downloads = 0
            for release in releases:
                # 累计所有assets的下载量
                for asset in release.get('assets', []):
                    download_count = asset.get('download_count', 0)
                    total_downloads += download_count
            
            logger.info(f"成功获取仓库 {validated_repo_name} 的下载总量: {total_downloads}")
            return total_downloads
        except requests.exceptions.Timeout:
            logger.warning(f"获取GitHub仓库下载量超时 {validated_repo_name}")
            return 0
        except requests.exceptions.RequestException as e:
            logger.error(f"获取GitHub仓库下载量失败 {validated_repo_name}: {str(e)}")
            return 0
        except Exception as e:
            logger.error(f"获取GitHub仓库下载量异常 {validated_repo_name}: {str(e)}")
            return 0
    
    def fetch_software_list(self):
        """从远程获取软件列表"""
        # 避免重复请求
        if hasattr(self, '_is_fetching') and self._is_fetching:
            logger.warning("正在获取软件列表，请勿重复请求")
            return
            
        self._is_fetching = True
        url = "https://raw.githubusercontent.com/SECTL/SecStore-apply/master/apply/software_list.json"
        request = QNetworkRequest(QUrl(url))
        # 设置User-Agent以避免被某些网站拒绝
        request.setRawHeader(b"User-Agent", b"SecStore/1.0")
        reply = self.network_manager.get(request)
        # 为软件列表请求单独连接finished信号
        reply.finished.connect(lambda r=reply: self.on_software_list_received(r))
        
    def on_software_list_received(self, reply):
        """处理接收到的软件列表数据"""
        try:
            # 重置请求标志
            self._is_fetching = False
            
            if reply.error() == QNetworkReply.NoError:
                raw_data = reply.readAll().data()
                # logger.info(f"接收到的原始数据长度: {len(raw_data)}")
                
                # 检查数据是否为空
                if not raw_data or len(raw_data) == 0:
                    logger.warning("接收到的数据为空")
                    return
                
                # 检查数据类型，避免尝试解码二进制数据
                if len(raw_data) > 4 and raw_data.startswith(b'\x89PNG'):
                    logger.error("接收到的是PNG图片数据，而不是JSON文本")
                    logger.error(f"请求URL可能错误: {reply.url().toString()}")
                    return
                
                # 尝试解码为UTF-8文本
                try:
                    data = raw_data.decode('utf-8')
                except UnicodeDecodeError as e:
                    logger.error(f"数据解码失败: {str(e)}")
                    # logger.error(f"数据前50字节: {raw_data[:50]}")
                    # logger.error(f"请求URL: {reply.url().toString()}")
                    return
                
                # logger.info(f"解码后的文本长度: {len(data)}")
                
                # 尝试解析JSON数据
                try:
                    software_data = json.loads(data)
                except json.JSONDecodeError as je:
                    logger.error(f"JSON解析错误: {je}")
                    logger.error(f"错误位置: 行{je.lineno}, 列{je.colno}")
                    logger.error(f"错误附近的文本: {je.pos}位置周围")
                    return
                
                # 清空现有卡片
                for card in self.app_cards:
                    card.deleteLater()
                self.app_cards.clear()
                
                # 重置计数器
                self._loaded_cards_count = 0
                self._total_cards_count = 0
                
                # 解析新的JSON格式：外层是仓库名，内层是软件信息
                software_list = []
                for repo_name, software_info in software_data.items():
                    # 跳过注释或其他非软件条目
                    if repo_name.startswith("//") or not isinstance(software_info, dict):
                        continue
                    
                    # 先添加基本信息，stars和下载量将在多线程中获取
                    software_list.append({
                        'name': software_info.get("name", repo_name),
                        'category': software_info.get("category", "未分类"),
                        'description': software_info.get("description", "暂无简介"),
                        'icon': software_info.get("icon"),
                        'stars': 0,  # 默认值，将在多线程中更新
                        'downloads': 0,  # 默认值，将在多线程中更新
                        'banner': software_info.get("banner", ""),
                        'repo_name': repo_name,  # 保存仓库名用于后续获取数据
                        'url': software_info.get('url')  # 保存URL用于仓库名验证
                    })
                
                self._total_cards_count = len(software_list)
                logger.info(f"准备并发加载 {self._total_cards_count} 个应用卡片")
                
                # 使用线程池并发获取GitHub数据和创建卡片，优化并发避免卡死
                with ThreadPoolExecutor(max_workers=4) as executor:  # 减少线程数避免资源耗尽
                    # 首先为每个软件提交获取stars和下载量的任务
                    software_futures = {}  # 保存每个软件相关的future
                    
                    for software in software_list:
                        # 提交获取stars的任务
                        stars_future = executor.submit(self._fetch_github_stars_threaded, 
                                                     software['repo_name'], 
                                                     software['url'])
                        # 提交获取下载量的任务
                        downloads_future = executor.submit(self._fetch_github_downloads_threaded, 
                                                         software['repo_name'], 
                                                         software['url'])
                        
                        software_futures[software['name']] = {
                            'stars_future': stars_future,
                            'downloads_future': downloads_future,
                            'software': software
                        }
                    
                    # 等待所有数据获取完成并更新software_list，设置超时避免无限等待
                    completed_count = 0
                    for software_name, future_info in software_futures.items():
                        try:
                            # 获取stars和下载量数据，设置超时
                            stars = future_info['stars_future'].result(timeout=8)  # 8秒超时
                            downloads = future_info['downloads_future'].result(timeout=8)  # 8秒超时
                            
                            # 更新software_list中的数据
                            for software in software_list:
                                if software['name'] == software_name:
                                    software['stars'] = stars or 0
                                    software['downloads'] = downloads or 0
                                    completed_count += 1
                                    logger.info(f"更新软件 {software_name} 数据: stars={stars}, downloads={downloads}")
                                    break
                        except TimeoutError:
                            logger.warning(f"获取软件 {software_name} 的GitHub数据超时，使用默认值")
                            # 超时也更新数据
                            for software in software_list:
                                if software['name'] == software_name:
                                    software['stars'] = 0
                                    software['downloads'] = 0
                                    completed_count += 1
                                    break
                        except Exception as e:
                            logger.error(f"获取软件 {software_name} 的GitHub数据失败: {str(e)}")
                            # 异常也更新数据
                            for software in software_list:
                                if software['name'] == software_name:
                                    software['stars'] = 0
                                    software['downloads'] = 0
                                    completed_count += 1
                                    break
                    
                    logger.info(f"数据获取完成: {completed_count}/{len(software_list)} 个软件")
                    
                    # 保存所有软件数据到all_apps属性，用于相关推荐
                    self.all_apps = software_list.copy()
                    
                    # 所有数据获取完成后，在主线程中顺序创建卡片，避免并发UI操作
                    for software in software_list:
                        try:
                            success = self._create_card_task(software)
                            if not success:
                                logger.error(f"创建卡片失败: {software['name']}")
                        except Exception as e:
                            logger.error(f"创建卡片失败: {str(e)}")
                    
                    # 确保最终统一布局
                    QTimer.singleShot(200, lambda: self.layout_cards(force_refresh=True))
                
                logger.info(f"所有卡片加载完成，共加载 {len(self.app_cards)} 个应用卡片")
                
                # 如果当前有搜索文本，自动执行搜索过滤
                if hasattr(self, 'current_search_text') and self.current_search_text:
                    logger.info(f"检测到搜索文本 '{self.current_search_text}'，自动执行搜索过滤")
                    self.perform_search(self.current_search_text)
                else:
                    # 初始化过滤应用列表为所有应用
                    self.filtered_apps = self.all_apps.copy()
                    # 确保显示所有UI元素
                    self.show_search_ui_elements()
                    # 强制刷新布局以确保所有卡片正确显示
                    QTimer.singleShot(100, lambda: self.layout_cards(force_refresh=True))
            else:
                logger.error(f"获取软件列表失败: {reply.errorString()}")
                # 网络错误时重试一次
                if hasattr(self, '_retry_count') and self._retry_count < 1:
                    self._retry_count += 1
                    logger.info("正在进行重试...")
                    # 延迟1秒后重试
                    QTimer.singleShot(1000, self.fetch_software_list)
                else:
                    # 重置重试计数
                    self._retry_count = 0
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误: {str(e)}")
            logger.error(f"错误位置: 行{e.lineno}, 列{e.colno}")
            logger.error(f"错误附近的文本: {e.pos}位置周围")
        except Exception as e:
            logger.error(f"解析软件列表数据失败: {str(e)}")
        finally:
            # 确保重置请求标志
            self._is_fetching = False
            reply.deleteLater()
    
    def _create_card_task(self, software_info):
        """创建卡片的任务函数，简化版本避免事件循环卡死"""
        try:
            # 直接调用主线程方法创建卡片，避免事件循环
            QMetaObject.invokeMethod(self, "_create_card_in_main_thread", Qt.QueuedConnection, 
                                    Q_ARG(object, software_info['name']), 
                                    Q_ARG(object, software_info['category']), 
                                    Q_ARG(object, software_info['description']), 
                                    Q_ARG(object, software_info['icon']),
                                    Q_ARG(object, software_info['stars']),
                                    Q_ARG(object, software_info['downloads']),
                                    Q_ARG(object, software_info['banner']),
                                    Q_ARG(object, software_info.get('repo_name')))
            return True
        except Exception as e:
            logger.error(f"卡片创建任务失败: {str(e)}")
            return False
    
    @pyqtSlot(object, object, object, object, object, object, object, object)
    def _create_card_in_main_thread(self, name, app_type, description, icon_url=None, stars=0, downloads=0, banner="", repo_name=None):
        """在主线程中创建卡片的槽函数"""
        try:
            card = self.create_app_card(name, app_type, description, icon_url, stars, downloads, banner, repo_name)
            if card:
                # 根据软件类型确定分类
                category = self._get_category_by_app_type(app_type)
                
                # 将卡片添加到对应的分类中
                self._mutex.lock()
                try:
                    self.app_cards.append(card)
                    self.category_cards[category].append(card)
                    self._loaded_cards_count += 1
                    logger.info(f"成功加载应用卡片: {name} (分类: {category}, 进度: {self._loaded_cards_count}/{self._total_cards_count})")
                    
                    # 只在所有卡片加载完成后统一布局，避免频繁刷新
                    if self._loaded_cards_count >= self._total_cards_count:
                        logger.info(f"所有卡片加载完成，共加载 {self._loaded_cards_count} 个应用卡片")
                        # 延迟布局以避免UI阻塞
                        QTimer.singleShot(100, lambda: self.layout_cards(force_refresh=True))
                finally:
                    self._mutex.unlock()
        except Exception as e:
            logger.error(f"主线程卡片创建失败: {str(e)}")
    
    def _get_category_by_app_type(self, app_type):
        """根据软件类型确定所属分类"""
        # 定义分类关键词映射
        category_keywords = {
            "屏幕批注与白板软件": [
                "批注", "白板", "标注", "画板", "绘图", "手写", "电子白板", 
                "屏幕标注", "批注工具", "白板工具", "绘图工具", "手写工具"
            ],
            "课表与看板类软件": [
                "课表", "课程", "看板", "日程", "计划", "时间表", "课程表",
                "课表管理", "看板管理", "日程管理", "计划管理", "时间管理"
            ],
            "辅助类软件与实用工具": [
                "工具", "实用", "辅助", "助手", "增强", "优化", "管理",
                "系统工具", "实用工具", "辅助工具", "系统增强", "效率工具"
            ]
        }
        
        # 将软件类型转换为小写以便匹配
        app_type_lower = app_type.lower()
        
        # 检查每个分类的关键词
        for category, keywords in category_keywords.items():
            for keyword in keywords:
                if keyword.lower() in app_type_lower:
                    logger.info(f"应用 '{app_type}' 匹配分类 '{category}' (关键词: {keyword})")
                    return category
        
        # 如果没有匹配到任何分类，默认归为"辅助类软件与实用工具"
        logger.info(f"应用 '{app_type}' 未匹配到特定分类，默认归为 '辅助类软件与实用工具'")
        return "辅助类软件与实用工具"
    
    def create_app_card(self, name, app_type, description, icon_url=None, stars=0, downloads=0, banner="", repo_name=None):
        """创建单个应用卡片"""
        # 创建卡片容器
        card = QWidget()
        card.setObjectName("app_card")
        card.setFixedSize(350, 150)  # 设置统一的固定尺寸，确保所有卡片高度宽度一致
        
        # 卡片布局
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(15, 15, 15, 15)
        
        # 图标区域
        icon_widget = QWidget()
        icon_widget.setFixedSize(60, 60)
        icon_layout = QVBoxLayout(icon_widget)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建图标标签
        icon_label = BodyLabel()
        icon_label.setObjectName("app_icon")
        icon_label.setFixedSize(48, 48)
        icon_label.setAlignment(Qt.AlignCenter)
        
        # 设置默认图标或加载远程图标
        if icon_url:
            self.load_app_icon(icon_label, icon_url)
        else:
            # 设置默认图标
            self.set_default_icon(icon_label)
        
        icon_layout.addWidget(icon_label)
        
        # 软件信息区域
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(5)
        
        # 软件名称
        name_label = BodyLabel(name)
        name_label.setObjectName("app_name")
        name_label.setFont(QFont(load_custom_font(), 14))
        
        # 软件类型
        type_label = BodyLabel(app_type)
        type_label.setObjectName("app_type")
        type_label.setFont(QFont(load_custom_font(), 12))
        
        # 软件简介
        # 处理简介文本，最多显示15个字，超出部分用...代替
        display_desc = description if len(description) <= 25 else description[:25] + "..."
        desc_label = BodyLabel(display_desc)
        desc_label.setObjectName("app_description")
        desc_label.setWordWrap(True)
        desc_label.setFont(QFont(load_custom_font(), 9))
        
        # Stars和下载量显示区域
        stats_widget = QWidget()
        stats_layout = QHBoxLayout(stats_widget)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(10)
        
        # Stars显示
        stars_label = BodyLabel(f"⭐ {stars}")
        stars_label.setObjectName("app_stars")
        stars_label.setFont(QFont(load_custom_font(), 10))
        
        # 下载量显示
        downloads_label = BodyLabel(f"⬇️ {downloads}")
        downloads_label.setObjectName("app_downloads")
        downloads_label.setFont(QFont(load_custom_font(), 10))
        
        # 添加到统计布局
        stats_layout.addWidget(stars_label)
        stats_layout.addWidget(downloads_label)
        stats_layout.addStretch()
        
        # 添加到信息布局
        info_layout.addWidget(name_label)
        info_layout.addWidget(type_label)
        info_layout.addWidget(desc_label)
        info_layout.addWidget(stats_widget)
        
        # 详情按钮
        detail_btn = QPushButton("详情")
        detail_btn.setObjectName("detail_btn")
        detail_btn.setFixedSize(80, 32)
        detail_btn.setFont(QFont(load_custom_font(), 16))
        detail_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
            QPushButton:pressed {
                background-color: #005a9e;
            }
        """)
        
        # 绑定点击事件，传递仓库名信息
        detail_btn.clicked.connect(lambda: self.show_app_detail(name, app_type, description, icon_url, stars, downloads, banner, repo_name))
        
        # 添加到卡片布局
        card_layout.addWidget(icon_widget)
        card_layout.addWidget(info_widget, stretch=1)
        card_layout.addWidget(detail_btn, alignment=Qt.AlignRight | Qt.AlignVCenter)
        
        # 设置卡片样式，根据主题判断
        if is_dark_theme:
            # 深色主题样式
            card.setStyleSheet("""
                #app_card {
                    background-color: #2d2d2d;
                    border: 1px solid #404040;
                    border-radius: 8px;
                }
                #app_card:hover {
                    border: 1px solid #0078d4;
                }
            """)
        else:
            # 浅色主题样式
            card.setStyleSheet("""
                #app_card {
                    background-color: white;
                    border: 1px solid #e0e0e0;
                    border-radius: 8px;
                }
                #app_card:hover {
                    border: 1px solid #0078d4;
                }
            """)
        
        return card

    def load_app_icon(self, icon_label, icon_url):
        """加载应用图标"""
        if not icon_url:
            logger.warning("图标URL为空，跳过加载")
            return
            
        try:
            logger.info(f"开始加载应用图标: {icon_url}")
            # 保存图标URL以便重试时使用
            icon_label._icon_url = icon_url
            # 初始化重试计数
            if not hasattr(icon_label, '_icon_retry_count'):
                icon_label._icon_retry_count = 0
                
            # 转换GitHub blob URL为raw URL
            processed_url = self.convert_github_url(icon_url)
            # logger.info(f"原始URL: {icon_url}")
            # logger.info(f"处理后URL: {processed_url}")
            
            # 创建网络请求获取图标
            request = QNetworkRequest(QUrl(processed_url))
            # 设置User-Agent以避免被某些网站拒绝
            request.setRawHeader(b"User-Agent", b"SecStore/1.0")
            reply = self.network_manager.get(request)
            logger.info(f"发送网络请求: {processed_url}")
            
            # 使用functools.partial确保参数正确传递
            reply.finished.connect(functools.partial(self._safe_on_icon_loaded, icon_label=icon_label))
        except Exception as e:
            logger.error(f"加载图标失败: {str(e)}")
            self.set_default_icon(icon_label)
    
    def convert_github_url(self, url):
        """转换GitHub blob URL为可直接访问的raw URL"""
        if not url:
            return url
            
        # 检查是否是GitHub blob URL
        if "github.com" in url and "/blob/" in url:
            # 将 github.com/username/repo/blob/branch 转换为 raw.githubusercontent.com/username/repo/branch
            raw_url = url.replace("github.com", "raw.githubusercontent.com")
            raw_url = raw_url.replace("/blob/", "/")
            return raw_url
        
        # 如果不是GitHub blob URL，直接返回原URL
        return url
        
    def set_default_icon(self, icon_label):
        """设置默认图标"""
        logger.info("开始设置默认图标")
        # 检查BodyLabel对象是否仍然有效
        if not icon_label or sip.isdeleted(icon_label):
            logger.warning("BodyLabel对象已被删除，无法设置默认图标")
            return
            
        try:
            logger.info("清除图标标签现有内容")
            icon_label.clear()  # 清除现有内容
            logger.info("设置默认图标样式")
            icon_label.setStyleSheet("""
                BodyLabel {
                    background-color: #f0f0f0;
                    border: 2px dashed #cccccc;
                    border-radius: 8px;
                }
            """)
            logger.info("设置默认图标文本")
            icon_label.setText("图标")
            logger.info("默认图标设置完成")
        except Exception as e:
            logger.error(f"设置默认图标失败: {str(e)}")
            
    def _safe_on_icon_loaded(self, icon_label):
        """安全处理图标加载完成事件，先检查对象有效性"""
        # 从信号发送者获取reply对象
        reply = self.sender()
        if not reply:
            logger.error("无法获取网络回复对象")
            return
            
        # logger.info("网络请求完成，开始处理图标")
        
        # 检查BodyLabel对象是否仍然有效
        if not icon_label or sip.isdeleted(icon_label):
            logger.warning("BodyLabel对象已被删除，跳过图标处理")
            reply.deleteLater()
            return
        
        # 对象有效，调用实际的图标加载处理方法
        self.on_icon_loaded(reply, icon_label)
    
    def on_icon_loaded(self, reply, icon_label):
        """处理图标加载完成事件"""
        try:
            # 检查BodyLabel对象是否仍然有效
            if not icon_label or sip.isdeleted(icon_label):
                logger.warning("BodyLabel对象已被删除，跳过图标处理")
                return
                
            if reply.error() == QNetworkReply.NoError:
                # logger.info("图标网络请求成功")
                data = reply.readAll()
                if data.isEmpty():
                    # logger.warning("图标数据为空")
                    # 尝试重新加载图标（重试一次）
                    if hasattr(icon_label, '_icon_retry_count') and icon_label._icon_retry_count < 1:
                        icon_label._icon_retry_count += 1
                        # logger.info("尝试重新加载图标...")
                        # 延迟2秒后重试
                        QTimer.singleShot(2000, lambda: self.load_app_icon(icon_label, icon_label._icon_url))
                    else:
                        # 重置重试计数并设置默认图标
                        icon_label._icon_retry_count = 0
                        self.set_default_icon(icon_label)
                    return
                    
                # logger.info(f"接收到图标数据，大小: {data.size()} 字节")
                pixmap = QPixmap()
                if pixmap.loadFromData(data):
                    # 缩放图标以适应标签大小
                    scaled_pixmap = pixmap.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    icon_label.setPixmap(scaled_pixmap)
                    logger.info("图标加载成功并显示")
                    # 重置重试计数
                    icon_label._icon_retry_count = 0
                else:
                    logger.warning(f"无法解析图标数据，数据大小: {data.size()}")
                    # 尝试重新加载图标
                    if hasattr(icon_label, '_icon_retry_count') and icon_label._icon_retry_count < 1:
                        icon_label._icon_retry_count += 1
                        logger.info("尝试重新加载图标...")
                        QTimer.singleShot(2000, lambda: self.load_app_icon(icon_label, icon_label._icon_url))
                    else:
                        icon_label._icon_retry_count = 0
                        self.set_default_icon(icon_label)
            else:
                logger.error(f"图标网络请求失败: {reply.errorString()}")
                # 网络错误时重试
                if hasattr(icon_label, '_icon_retry_count') and icon_label._icon_retry_count < 1:
                    icon_label._icon_retry_count += 1
                    logger.info("尝试重新加载图标...")
                    QTimer.singleShot(2000, lambda: self.load_app_icon(icon_label, icon_label._icon_url))
                else:
                    icon_label._icon_retry_count = 0
                    self.set_default_icon(icon_label)
        except Exception as e:
            logger.error(f"处理图标数据失败: {str(e)}")
            # 在异常处理中也要检查对象是否有效
            if icon_label and not sip.isdeleted(icon_label):
                self.set_default_icon(icon_label)
        finally:
            reply.deleteLater()
    
    def show_app_detail(self, name, app_type, description, icon_url, stars=0, downloads=0, banner="", repo_name=None):
        """显示应用详情对话框"""
        detail_dialog = AppDetailDialog(name, app_type, description, icon_url, stars, downloads, banner, repo_name, self)
        detail_dialog.exec_()


class AppDetailDialog(QDialog):
    """应用详情对话框"""
    def __init__(self, name, app_type, description, icon_url, stars=0, downloads=0, banner="", repo_name=None, parent=None):
        super().__init__(parent)
        self.name = name
        self.app_type = app_type
        self.description = description
        self.icon_url = icon_url
        self.stars = stars
        self.downloads = downloads
        self.banner = banner
        self.repo_name = repo_name
        
        self.setObjectName("app_detail_dialog")
        self.setWindowTitle(f"{name} - 详情")
        self.setFixedSize(600, 700)
        self.setModal(True)
        
        # 初始化UI
        self.init_ui()
        
        # 加载图标
        self.load_icon()
        
        # 加载banner图片
        if self.banner:
            self.load_banner()
        
        # 获取更新日志
        self.fetch_changelog()
        
    def init_ui(self):
        """初始化用户界面"""
        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # Banner图片区域
        if self.banner:
            self.banner_widget = QWidget()
            self.banner_widget.setFixedHeight(150)
            self.banner_widget.setObjectName("detail_banner_widget")
            banner_layout = QVBoxLayout(self.banner_widget)
            banner_layout.setContentsMargins(0, 0, 0, 0)
            
            self.banner_label = BodyLabel()
            self.banner_label.setObjectName("detail_banner_label")
            self.banner_label.setFixedSize(560, 150)
            self.banner_label.setAlignment(Qt.AlignCenter)
            self.banner_label.setScaledContents(True)
            
            banner_layout.addWidget(self.banner_label, alignment=Qt.AlignCenter)
            main_layout.addWidget(self.banner_widget)
        
        # 顶部信息区域
        top_widget = QWidget()
        top_layout = QHBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(15)
        
        # 图标容器
        self.icon_widget = QWidget()
        self.icon_widget.setFixedSize(80, 80)
        self.icon_widget.setObjectName("detail_icon_widget")
        icon_layout = QVBoxLayout(self.icon_widget)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        
        self.icon_label = BodyLabel()
        self.icon_label.setObjectName("detail_icon_label")
        self.icon_label.setFixedSize(64, 64)
        self.icon_label.setAlignment(Qt.AlignCenter)
        icon_layout.addWidget(self.icon_label, alignment=Qt.AlignCenter)
        
        # 应用信息
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(5)
        
        # 应用名称
        name_label = TitleLabel(self.name)
        name_label.setObjectName("detail_app_name")
        name_label.setFont(QFont(load_custom_font(), 18))
        
        # 应用类型
        type_label = BodyLabel(f"类型: {self.app_type}")
        type_label.setObjectName("detail_app_type")
        type_label.setFont(QFont(load_custom_font(), 12))
        
        # 应用简介
        desc_label = BodyLabel(self.description)
        desc_label.setObjectName("detail_app_description")
        desc_label.setWordWrap(True)
        desc_label.setFont(QFont(load_custom_font(), 10))
        
        # 统计信息区域
        stats_widget = QWidget()
        stats_layout = QHBoxLayout(stats_widget)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(15)
        
        # Stars显示
        stars_label = BodyLabel(f"⭐ {self.stars}")
        stars_label.setObjectName("detail_stars")
        stars_label.setFont(QFont(load_custom_font(), 12))
        
        # 下载量显示
        downloads_label = BodyLabel(f"⬇️ {self.downloads}")
        downloads_label.setObjectName("detail_downloads")
        downloads_label.setFont(QFont(load_custom_font(), 12))
        
        stats_layout.addWidget(stars_label)
        stats_layout.addWidget(downloads_label)
        stats_layout.addStretch()
        
        info_layout.addWidget(name_label)
        info_layout.addWidget(type_label)
        info_layout.addWidget(desc_label)
        info_layout.addWidget(stats_widget)
        info_layout.addStretch()
        
        # 添加到顶部布局
        top_layout.addWidget(self.icon_widget)
        top_layout.addWidget(info_widget, stretch=1)
        
        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        
        # 更新日志区域
        changelog_widget = QWidget()
        changelog_layout = QVBoxLayout(changelog_widget)
        changelog_layout.setContentsMargins(0, 0, 0, 0)
        changelog_layout.setSpacing(10)
        
        changelog_title = SubtitleLabel("更新日志")
        changelog_title.setObjectName("detail_changelog_title")
        
        # 更新日志内容区域
        self.changelog_content = TextBrowser()
        self.changelog_content.setObjectName("detail_changelog_content")
        self.changelog_content.setReadOnly(True)
        self.changelog_content.setMaximumHeight(200)
        self.changelog_content.setFont(QFont(load_custom_font(), 9))
        
        changelog_layout.addWidget(changelog_title)
        changelog_layout.addWidget(self.changelog_content)
        
        # 相关推荐区域
        recommend_widget = QWidget()
        recommend_layout = QVBoxLayout(recommend_widget)
        recommend_layout.setContentsMargins(0, 0, 0, 0)
        recommend_layout.setSpacing(10)
        
        recommend_title = SubtitleLabel("相关推荐")
        recommend_title.setObjectName("detail_recommend_title")
        
        # 相关推荐内容容器
        self.recommend_content_widget = QWidget()
        self.recommend_layout_inner = QVBoxLayout(self.recommend_content_widget)
        self.recommend_layout_inner.setContentsMargins(0, 0, 0, 0)
        self.recommend_layout_inner.setSpacing(10)
        
        # 占位文本
        self.recommend_placeholder = BodyLabel("正在加载相关推荐...")
        self.recommend_placeholder.setObjectName("detail_recommend_content")
        self.recommend_placeholder.setWordWrap(True)
        self.recommend_placeholder.setFont(QFont(load_custom_font(), 9))
        self.recommend_layout_inner.addWidget(self.recommend_placeholder)
        
        recommend_layout.addWidget(recommend_title)
        recommend_layout.addWidget(self.recommend_content_widget)
        
        # 底部按钮区域
        button_widget = QWidget()
        button_layout = QHBoxLayout(button_widget)
        button_layout.setContentsMargins(0, 0, 0, 0)
        
        # 关闭按钮
        close_btn = PushButton("关闭")
        close_btn.setObjectName("detail_close_btn")
        close_btn.setFixedSize(80, 32)
        close_btn.setFont(QFont(load_custom_font(), 12))
        close_btn.clicked.connect(self.close)
        
        # 安装按钮
        install_btn = PrimaryPushButton("安装")
        install_btn.setObjectName("detail_install_btn")
        install_btn.setFixedSize(80, 32)
        install_btn.setFont(QFont(load_custom_font(), 12))
        install_btn.clicked.connect(self.install_app)
        
        button_layout.addStretch()
        button_layout.addWidget(install_btn)
        button_layout.addWidget(close_btn)
        
        # 添加到主布局
        main_layout.addWidget(top_widget)
        main_layout.addWidget(line)
        main_layout.addWidget(changelog_widget)
        main_layout.addWidget(recommend_widget)
        main_layout.addStretch()
        main_layout.addWidget(button_widget)
        
        # 设置样式
        self.set_style()
        
        # 加载相关推荐
        self.load_related_recommendations()

    def validate_and_fix_repo_name(self, repo_name, url=None):
        """验证并修正仓库名格式，从url中获取正确的组织信息"""
        if not repo_name:
            return None
            
        # 如果仓库名格式正确（包含/），直接返回
        if '/' in repo_name:
            return repo_name
            
        # 如果仓库名不包含/，尝试从url中提取组织信息
        if url and 'github.com' in url:
            try:
                # 从GitHub URL中提取用户名/组织名和仓库名
                if '/blob/' in url:
                    # 处理blob URL: github.com/username/repo/blob/branch/path
                    url_parts = url.split('github.com/')[1].split('/')
                    if len(url_parts) >= 2:
                        username = url_parts[0]
                        repo_name_from_url = url_parts[1]
                        return f"{username}/{repo_name_from_url}"
                else:
                    # 处理其他GitHub URL格式
                    url_parts = url.split('github.com/')[1].split('/')
                    if len(url_parts) >= 2:
                        return f"{url_parts[0]}/{url_parts[1]}"
            except Exception as e:
                logger.warning(f"从URL提取仓库名失败: {e}")
        
        logger.warning(f"无法确定仓库名的正确格式: {repo_name}")
        return None
        
    def set_style(self):
        """设置对话框样式"""
        if is_dark_theme:
            # 深色主题样式
            self.setStyleSheet("""
                #app_detail_dialog {
                    background-color: #2d2d2d;
                    color: white;
                }
                #detail_icon_widget {
                    background-color: #404040;
                    border: 1px solid #555555;
                    border-radius: 8px;
                }
                #detail_banner_widget {
                    background-color: #404040;
                    border: 1px solid #555555;
                    border-radius: 8px;
                }
                #detail_changelog_content {
                    background-color: #404040;
                    border: 1px solid #555555;
                    border-radius: 4px;
                    color: white;
                }
                QFrame[frameShape="4"] {
                    color: #555555;
                }
            """)
        else:
            # 浅色主题样式
            self.setStyleSheet("""
                #app_detail_dialog {
                    background-color: white;
                    color: black;
                }
                #detail_icon_widget {
                    background-color: #f8f9fa;
                    border: 1px solid #e0e0e0;
                    border-radius: 8px;
                }
                #detail_banner_widget {
                    background-color: #f8f9fa;
                    border: 1px solid #e0e0e0;
                    border-radius: 8px;
                }
                #detail_changelog_content {
                    background-color: #f8f9fa;
                    border: 1px solid #e0e0e0;
                    border-radius: 4px;
                    color: black;
                }
                QFrame[frameShape="4"] {
                    color: #e0e0e0;
                }
            """)

    def convert_github_url(self, url):
        """转换GitHub blob URL为可直接访问的raw URL"""
        if not url:
            return url
            
        # 检查是否是GitHub blob URL
        if "github.com" in url and "/blob/" in url:
            # 将 github.com/username/repo/blob/branch 转换为 raw.githubusercontent.com/username/repo/branch
            raw_url = url.replace("github.com", "raw.githubusercontent.com")
            raw_url = raw_url.replace("/blob/", "/")
            return raw_url
        
        # 如果不是GitHub blob URL，直接返回原URL
        return url
    
    def load_icon(self):
        """加载应用图标"""
        if not self.icon_url:
            self.set_default_icon()
            return
            
        try:
            # 转换GitHub blob URL为raw URL
            processed_url = self.parent().convert_github_url(self.icon_url)
            
            # 创建网络请求获取图标
            request = QNetworkRequest(QUrl(processed_url))
            request.setRawHeader(b"User-Agent", b"SecStore/1.0")
            reply = self.parent().network_manager.get(request)
            
            reply.finished.connect(lambda r=reply: self.on_icon_loaded(r))
        except Exception as e:
            logger.error(f"加载详情图标失败: {str(e)}")
            self.set_default_icon()
    
    def load_banner(self):
        """加载banner图片"""
        if not self.banner:
            return
            
        try:
            # 转换GitHub blob URL为raw URL
            processed_url = self.parent().convert_github_url(self.banner)
            
            # 创建网络请求获取banner图片
            request = QNetworkRequest(QUrl(processed_url))
            request.setRawHeader(b"User-Agent", b"SecStore/1.0")
            reply = self.parent().network_manager.get(request)
            
            reply.finished.connect(lambda r=reply: self.on_banner_loaded(r))
        except Exception as e:
            logger.error(f"加载banner图片失败: {str(e)}")
    
    def on_icon_loaded(self, reply):
        """处理图标加载完成事件"""
        try:
            if reply.error() == QNetworkReply.NoError:
                data = reply.readAll()
                if not data.isEmpty():
                    pixmap = QPixmap()
                    if pixmap.loadFromData(data):
                        # 缩放图标以适应标签大小
                        scaled_pixmap = pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        self.icon_label.setPixmap(scaled_pixmap)
                        return
            
            # 加载失败时设置默认图标
            self.set_default_icon()
        except Exception as e:
            logger.error(f"处理详情图标失败: {str(e)}")
            self.set_default_icon()
        finally:
            reply.deleteLater()
    
    def on_banner_loaded(self, reply):
        """处理banner图片加载完成事件"""
        try:
            if reply.error() == QNetworkReply.NoError:
                data = reply.readAll()
                if not data.isEmpty():
                    pixmap = QPixmap()
                    if pixmap.loadFromData(data):
                        # 缩放banner图片以适应标签大小
                        scaled_pixmap = pixmap.scaled(560, 150, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                        self.banner_label.setPixmap(scaled_pixmap)
                        return
            
            # 加载失败时隐藏banner区域
            if hasattr(self, 'banner_widget'):
                self.banner_widget.hide()
        except Exception as e:
            logger.error(f"处理banner图片失败: {str(e)}")
            if hasattr(self, 'banner_widget'):
                self.banner_widget.hide()
        finally:
            reply.deleteLater()
    
    def set_default_icon(self):
        """设置默认图标"""
        self.icon_label.clear()
        self.icon_label.setStyleSheet("""
            BodyLabel {
                background-color: #f0f0f0;
                border: 2px dashed #cccccc;
                border-radius: 8px;
            }
        """)
        self.icon_label.setText("图标")
    
    def fetch_changelog(self):
        """获取更新日志"""
        # 显示加载状态
        self.changelog_content.setText("正在获取更新日志...")
        
        # 从GitHub仓库获取发布信息
        self.fetch_github_releases()
    
    def fetch_github_releases(self):
        """从GitHub仓库获取发布信息"""
        try:
            # 使用动态仓库名，如果没有则使用默认值
            repo_name = self.repo_name if self.repo_name else "SECTL/SecStore"
            
            # 验证并修正仓库名格式，尝试从icon_url获取GitHub URL信息
            validated_repo_name = self.parent().validate_and_fix_repo_name(repo_name, self.icon_url)
            if not validated_repo_name:
                logger.error(f"仓库名格式不正确且无法修正: {repo_name}，无法获取发布信息")
                self.changelog_content.setText("无法获取更新日志：仓库名格式不正确")
                return
            
            logger.info(f"获取仓库 {validated_repo_name} 的发布信息")
            
            # GitHub API URL获取仓库发布信息
            api_url = f"https://api.github.com/repos/{validated_repo_name}/releases"
            
            # 创建网络请求
            request = QNetworkRequest(QUrl(api_url))
            request.setRawHeader(b"User-Agent", b"SecStore/1.0")
            request.setRawHeader(b"Accept", b"application/vnd.github.v3+json")
            
            reply = self.parent().network_manager.get(request)
            reply.finished.connect(lambda r=reply: self.on_releases_loaded(r))
            
            logger.info("已发送GitHub发布信息请求")
        except Exception as e:
            logger.error(f"获取GitHub发布信息失败: {str(e)}")
            self.changelog_content.setText("获取更新日志失败")
    
    def on_releases_loaded(self, reply):
        """处理GitHub发布信息加载完成事件"""
        try:
            if reply.error() == QNetworkReply.NoError:
                data = reply.readAll()
                if not data.isEmpty():
                    # 解析JSON数据
                    import json
                    releases = json.loads(data.data().decode('utf-8'))
                    
                    if releases and len(releases) > 0:
                        # 格式化发布信息为更新日志
                        changelog_text = self.format_releases_to_changelog(releases)
                        self.changelog_content.setText(changelog_text)
                        logger.info("成功获取并显示GitHub发布信息")
                        return
                    else:
                        logger.warning("GitHub仓库没有发布信息")
                else:
                    logger.warning("GitHub API返回空数据")
            else:
                logger.error(f"GitHub API请求失败: {reply.errorString()}")
        except Exception as e:
            logger.error(f"处理GitHub发布信息失败: {str(e)}")
        finally:
            reply.deleteLater()
    
    def format_releases_to_changelog(self, releases):
        """将GitHub发布信息格式化为更新日志文本"""
        changelog_lines = []
        
        # 只显示最新的3个发布版本
        for i, release in enumerate(releases[:3]):
            version = release.get('name', '未知版本')
            published_at = release.get('published_at', '')
            body = release.get('body', '')
            
            # 格式化日期
            if published_at:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                    formatted_date = dt.strftime('%Y-%m-%d')
                except:
                    formatted_date = published_at[:10] if len(published_at) >= 10 else published_at
            else:
                formatted_date = '未知日期'
            
            # 添加版本标题
            changelog_lines.append(f"版本 {version} ({formatted_date})")
            changelog_lines.append("=" * 40)
            
            # 处理发布内容
            if body:
                # 移除Markdown链接格式，保留文本
                import re
                # 移除图片链接 ![alt](url)
                body = re.sub(r'!\[.*?\]\(.*?\)', '', body)
                # 移除普通链接 [text](url) -> text
                body = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', body)
                # 移除多余的空行
                body = re.sub(r'\n\s*\n\s*\n', '\n\n', body)
                # 移除行首的#符号
                body = re.sub(r'^#+\s*', '', body, flags=re.MULTILINE)
                # 将项目符号改为•
                body = re.sub(r'^[\*\-]\s+', '• ', body, flags=re.MULTILINE)
                
                # 添加处理后的内容
                changelog_lines.append(body.strip())
            else:
                changelog_lines.append("• 暂无更新内容")
            
            # 添加分隔空行
            if i < len(releases[:3]) - 1:
                changelog_lines.append("")
                changelog_lines.append("")
        
        return '\n'.join(changelog_lines)
    
    def load_related_recommendations(self):
        """加载相关推荐软件"""
        try:
            # 获取父窗口的所有软件数据
            all_apps = getattr(self.parent(), 'all_apps', [])
            if not all_apps:
                logger.warning("无法获取软件列表数据")
                self.recommend_placeholder.setText("暂无相关推荐")
                return
            
            # 获取当前软件的标签
            current_category = self.app_type
            if not current_category:
                logger.warning("当前软件没有标签信息")
                self.recommend_placeholder.setText("暂无相关推荐")
                return
            
            # 筛选同标签的软件（排除当前软件）
            related_apps = []
            for app in all_apps:
                if (app.get('category') == current_category and 
                    app.get('name') != self.name):
                    related_apps.append(app)
            
            if not related_apps:
                self.recommend_placeholder.setText("暂无同标签软件")
                return
            
            # 按stars数和下载数排序（综合评分：stars * 0.6 + downloads * 0.4）
            def calculate_score(app):
                stars = app.get('stars', 0)
                downloads = app.get('downloads', 0)
                return stars * 0.6 + downloads * 0.4
            
            related_apps.sort(key=calculate_score, reverse=True)
            
            # 取前5个软件
            top_apps = related_apps[:5]
            
            # 清空占位文本
            self.recommend_placeholder.hide()
            
            # 清空现有推荐内容
            while self.recommend_layout_inner.count():
                item = self.recommend_layout_inner.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            
            # 创建推荐软件卡片
            for app in top_apps:
                app_card = self.create_recommend_card(app)
                self.recommend_layout_inner.addWidget(app_card)
                
            logger.info(f"成功加载 {len(top_apps)} 个相关推荐软件")
            
        except Exception as e:
            logger.error(f"加载相关推荐失败: {str(e)}")
            self.recommend_placeholder.setText("加载推荐失败")
    
    def create_recommend_card(self, app):
        """创建单个推荐软件卡片"""
        card = QWidget()
        card.setObjectName("recommend_card")
        card.setFixedHeight(60)
        
        layout = QHBoxLayout(card)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(10)
        
        # 软件图标
        icon_label = BodyLabel()
        icon_label.setFixedSize(40, 40)
        icon_label.setObjectName("recommend_card_icon")
        
        # 加载图标
        icon_url = app.get('icon')
        if icon_url:
            try:
                processed_url = self.parent().convert_github_url(icon_url)
                request = QNetworkRequest(QUrl(processed_url))
                request.setRawHeader(b"User-Agent", b"SecStore/1.0")
                reply = self.parent().network_manager.get(request)
                reply.finished.connect(lambda r=reply, label=icon_label: self.on_recommend_icon_loaded(r, label))
            except Exception as e:
                logger.error(f"加载推荐图标失败: {str(e)}")
                icon_label.setText("图标")
        else:
            icon_label.setText("图标")
        
        # 软件信息
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2)
        
        # 软件名称
        name_label = BodyLabel(app.get('name', '未知软件'))
        name_label.setObjectName("recommend_card_name")
        name_label.setFont(QFont(load_custom_font(), 10, QFont.Bold))
        
        # 软件统计信息
        stats_label = BodyLabel(f"⭐ {app.get('stars', 0)}  📥 {app.get('downloads', 0)}")
        stats_label.setObjectName("recommend_card_stats")
        stats_label.setFont(QFont(load_custom_font(), 8))
        
        info_layout.addWidget(name_label)
        info_layout.addWidget(stats_label)
        
        # 查看详情按钮
        detail_btn = PushButton("查看详情")
        detail_btn.setFixedSize(70, 30)
        detail_btn.setFont(QFont(load_custom_font(), 8))
        detail_btn.clicked.connect(lambda checked, a=app: self.show_related_app_detail(a))
        
        layout.addWidget(icon_label)
        layout.addWidget(info_widget)
        layout.addStretch()
        layout.addWidget(detail_btn)
        
        # 设置卡片样式
        card.setStyleSheet("""
            #recommend_card {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
            }
            #recommend_card:hover {
                background-color: rgba(255, 255, 255, 0.1);
            }
            #recommend_card_icon {
                background-color: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 4px;
                color: rgba(255, 255, 255, 0.7);
            }
            #recommend_card_name {
                color: white;
            }
            #recommend_card_stats {
                color: rgba(255, 255, 255, 0.7);
            }
        """)
        
        return card
    
    def on_recommend_icon_loaded(self, reply, label):
        """处理推荐图标加载完成事件"""
        try:
            if reply.error() == QNetworkReply.NoError:
                data = reply.readAll()
                if not data.isEmpty():
                    pixmap = QPixmap()
                    if pixmap.loadFromData(data):
                        scaled_pixmap = pixmap.scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        label.setPixmap(scaled_pixmap)
                        return
            # 加载失败时设置默认文本
            label.setText("图标")
        except Exception as e:
            logger.error(f"处理推荐图标失败: {str(e)}")
            label.setText("图标")
        finally:
            reply.deleteLater()
    
    def show_related_app_detail(self, app):
        """显示相关软件的详情"""
        try:
            # 创建新的详情对话框
            detail_dialog = AppDetailDialog(
                app.get('name', '未知软件'),
                app.get('category', '未分类'),
                app.get('description', '暂无简介'),
                app.get('icon'),
                app.get('stars', 0),
                app.get('downloads', 0),
                app.get('banner', ''),
                app.get('repo_name'),
                self.parent()
            )
            detail_dialog.exec_()
        except Exception as e:
            logger.error(f"显示相关软件详情失败: {str(e)}")
            QMessageBox.warning(self, "错误", "无法显示软件详情")
    
    def install_app(self):
        """安装应用"""
        # TODO: 实现应用安装逻辑
        logger.info(f"开始安装应用: {self.name}")
        QMessageBox.information(self, "安装提示", f"正在准备安装 {self.name}...\n此功能正在开发中。")
