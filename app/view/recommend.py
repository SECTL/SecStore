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
from concurrent.futures import ThreadPoolExecutor, as_completed

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
        
        # 初始化网络管理器
        self.network_manager = QNetworkAccessManager()
        # 不再全局连接finished信号，而是为每个请求单独处理
        
        # 获取软件列表
        self.fetch_software_list()

        # 初始化UI
        self.init_ui()
        
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
        
    def create_recommend_cards(self):
        """创建推荐软件卡片"""
        # 创建推荐软件容器
        self.recommend_container = QWidget()
        self.recommend_container.setObjectName("recommend_container")
        recommend_layout = QVBoxLayout(self.recommend_container)
        recommend_layout.setContentsMargins(30, 20, 30, 20)
        recommend_layout.setSpacing(20)
        
        # 添加"推荐软件"标题
        title_label = TitleLabel("推荐软件")
        title_label.setObjectName("recommend_title")
        title_label.setAlignment(Qt.AlignLeft)
        recommend_layout.addWidget(title_label)
        
        # 创建卡片内容容器，用于动态布局
        self.cards_content_widget = QWidget()
        self.cards_content_widget.setObjectName("cards_content_widget")
        recommend_layout.addWidget(self.cards_content_widget)
        
        # 卡片布局将在layout_cards方法中动态创建
        
        # 设置滚动区域引用
        self.scroll_area = self.main_scroll_area
        
        # 初始化卡片列表
        self.app_cards = []
        
        # 初始布局卡片
        self.layout_cards()
        
        # 添加到主布局
        self.main_content_layout.addWidget(self.cards_content_widget, alignment=Qt.AlignHCenter)

    def layout_cards(self):
        """动态布局卡片，根据窗口宽度自动调整每行显示的卡片数量"""
        if not self.cards_content_widget:
            return
            
        # 计算每行应该显示的卡片数量
        container_width = self.width() - 40  # 减去左右边距
        card_width = 350
        card_spacing = 15
        
        # 计算每行最多能显示的卡片数量
        max_cards_per_row = max(1, int((container_width + card_spacing) / (card_width + card_spacing)))
        
        # 检查布局是否真的需要改变
        if hasattr(self, '_last_max_cards_per_row'):
            if self._last_max_cards_per_row == max_cards_per_row:
                return  # 布局没有变化，不需要重排
        self._last_max_cards_per_row = max_cards_per_row
        
        # 设置窗口不更新，减少闪烁
        self.setUpdatesEnabled(False)
        
        try:
            # 清空现有布局
            layout = self.cards_content_widget.layout()
            if layout:
                # 删除布局中的所有部件
                while layout.count():
                    item = layout.takeAt(0)
                    if item.widget():
                        item.widget().deleteLater()
                # 删除旧的布局对象
                QWidget().setLayout(layout)
            
            # 重新创建布局
            self.cards_layout = QVBoxLayout(self.cards_content_widget)
            self.cards_layout.setContentsMargins(0, 0, 0, 0)
            self.cards_layout.setSpacing(20)
            self.cards_layout.setAlignment(Qt.AlignHCenter)
            
            # 创建当前行容器
            current_row = QWidget()
            current_row.setObjectName("cards_row")
            row_layout = QHBoxLayout(current_row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(card_spacing)
            row_layout.setAlignment(Qt.AlignHCenter)
            
            # 动态布局卡片
            for i, card in enumerate(self.app_cards):
                # 如果当前行已满，创建新行
                if i > 0 and i % max_cards_per_row == 0:
                    # 添加两侧拉伸因子，使卡片居中对齐
                    row_layout.addStretch(1)
                    row_layout.insertStretch(0, 1)
                    # 将当前行添加到内容容器
                    self.cards_layout.addWidget(current_row)
                    
                    # 创建新的一行
                    current_row = QWidget()
                    current_row.setObjectName("cards_row")
                    row_layout = QHBoxLayout(current_row)
                    row_layout.setContentsMargins(0, 0, 0, 0)
                    row_layout.setSpacing(card_spacing)
                    row_layout.setAlignment(Qt.AlignHCenter)
                
                # 将卡片添加到当前行
                row_layout.addWidget(card)
            
            # 添加最后一行的拉伸因子和布局，使卡片居中对齐
            row_layout.addStretch(1)
            row_layout.insertStretch(0, 1)
            self.cards_layout.addWidget(current_row)
        
        finally:
            # 恢复窗口更新
            self.setUpdatesEnabled(True)
            # 强制重绘
            self.update()
    
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
        
        # 延迟重新布局，避免频繁调用
        QTimer.singleShot(200, self.layout_cards)
        
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
                    
                    # 从GitHub API获取真实的stars数量
                    github_stars = self.fetch_github_stars(repo_name, software_info.get('url'))
                    # 从GitHub API获取真实的下载量数据
                    github_downloads = self.fetch_github_downloads(repo_name, software_info.get('url'))
                    
                    software_list.append({
                        'name': software_info.get("name", repo_name),
                        'category': software_info.get("category", "未分类"),
                        'description': software_info.get("description", "暂无简介"),
                        'icon': software_info.get("icon"),
                        'stars': github_stars,  # 使用GitHub API获取的真实stars数据
                        'downloads': github_downloads,  # 使用GitHub API获取的真实下载量数据
                        'banner': software_info.get("banner", "")
                    })
                
                self._total_cards_count = len(software_list)
                logger.info(f"准备并发加载 {self._total_cards_count} 个应用卡片")
                
                # 使用线程池并发创建卡片
                with ThreadPoolExecutor(max_workers=8) as executor:
                    # 提交所有卡片创建任务
                    future_to_card = {
                        executor.submit(self._create_card_task, software): software 
                        for software in software_list
                    }
                    
                    # 处理完成的任务
                    for future in as_completed(future_to_card):
                        software = future_to_card[future]
                        try:
                            success = future.result()
                            if not success:
                                logger.error(f"创建卡片失败 {software['name']}")
                        except Exception as e:
                            logger.error(f"创建卡片失败 {software['name']}: {str(e)}")
                
                logger.info(f"所有卡片加载完成，共加载 {len(self.app_cards)} 个应用卡片")
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
        """创建卡片的任务函数，用于多线程执行"""
        try:
            # 创建事件循环用于等待卡片创建完成
            card_created = QEventLoop()
            
            # 在主线程中执行卡片创建
            QMetaObject.invokeMethod(self, "_create_card_in_main_thread", Qt.QueuedConnection, 
                                    Q_ARG(object, software_info['name']), 
                                    Q_ARG(object, software_info['category']), 
                                    Q_ARG(object, software_info['description']), 
                                    Q_ARG(object, software_info['icon']),
                                    Q_ARG(object, software_info['stars']),
                                    Q_ARG(object, software_info['downloads']),
                                    Q_ARG(object, software_info['banner']))
            
            # 等待一小段时间确保卡片创建开始
            QTimer.singleShot(100, card_created.quit)
            card_created.exec_()
            
            return True
        except Exception as e:
            logger.error(f"卡片创建任务失败: {str(e)}")
            return False
    
    @pyqtSlot(object, object, object, object, object, object, object)
    def _create_card_in_main_thread(self, name, app_type, description, icon_url=None, stars=0, downloads=0, banner=""):
        """在主线程中创建卡片的槽函数"""
        try:
            card = self.create_app_card(name, app_type, description, icon_url, stars, downloads, banner)
            if card:
                # 将卡片添加到列表中
                self._mutex.lock()
                try:
                    self.app_cards.append(card)
                    self._loaded_cards_count += 1
                    logger.info(f"成功加载应用卡片: {name} (进度: {self._loaded_cards_count}/{self._total_cards_count})")
                    
                    # 每加载一个卡片就重新布局
                    self.layout_cards()
                    
                    # 检查是否所有卡片都加载完成
                    if self._loaded_cards_count >= self._total_cards_count:
                        logger.info(f"所有卡片加载完成，共加载 {self._loaded_cards_count} 个应用卡片")
                finally:
                    self._mutex.unlock()
        except Exception as e:
            logger.error(f"主线程卡片创建失败: {str(e)}")
    
    def create_app_card(self, name, app_type, description, icon_url=None, stars=0, downloads=0, banner=""):
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
        icon_label.setScaledContents(True)
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
        
        # 绑定点击事件
        detail_btn.clicked.connect(lambda: self.show_app_detail(name, app_type, description, icon_url, stars, downloads, banner))
        
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
            return
            
        try:
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
            
            # 使用lambda函数处理图标下载完成事件，添加对象有效性检查
            reply.finished.connect(lambda r=reply, label=icon_label: self._safe_on_icon_loaded(r, label))
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
        # 检查BodyLabel对象是否仍然有效
        if not icon_label or sip.isdeleted(icon_label):
            logger.warning("BodyLabel对象已被删除，无法设置默认图标")
            return
            
        try:
            icon_label.clear()  # 清除现有内容
            icon_label.setStyleSheet("""
                BodyLabel {
                    background-color: #f0f0f0;
                    border: 2px dashed #cccccc;
                    border-radius: 8px;
                }
            """)
            icon_label.setText("图标")
            logger.info("已设置默认图标")
        except Exception as e:
            logger.error(f"设置默认图标失败: {str(e)}")
            
    def _safe_on_icon_loaded(self, reply, icon_label):
        """安全处理图标加载完成事件，先检查对象有效性"""
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
                data = reply.readAll()
                if data.isEmpty():
                    logger.warning("图标数据为空")
                    # 尝试重新加载图标（重试一次）
                    if hasattr(icon_label, '_icon_retry_count') and icon_label._icon_retry_count < 1:
                        icon_label._icon_retry_count += 1
                        logger.info("尝试重新加载图标...")
                        # 延迟2秒后重试
                        QTimer.singleShot(2000, lambda: self.load_app_icon(icon_label, icon_label._icon_url))
                    else:
                        # 重置重试计数并设置默认图标
                        icon_label._icon_retry_count = 0
                        self.set_default_icon(icon_label)
                    return
                    
                pixmap = QPixmap()
                if pixmap.loadFromData(data):
                    # 缩放图标以适应标签大小
                    scaled_pixmap = pixmap.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    icon_label.setPixmap(scaled_pixmap)
                    logger.info("图标加载成功")
                    # 重置重试计数
                    icon_label._icon_retry_count = 0
                else:
                    logger.warning(f"无法加载图标数据，数据大小: {data.size()}")
                    # 尝试重新加载图标
                    if hasattr(icon_label, '_icon_retry_count') and icon_label._icon_retry_count < 1:
                        icon_label._icon_retry_count += 1
                        logger.info("尝试重新加载图标...")
                        QTimer.singleShot(2000, lambda: self.load_app_icon(icon_label, icon_label._icon_url))
                    else:
                        icon_label._icon_retry_count = 0
                        self.set_default_icon(icon_label)
            else:
                logger.error(f"获取图标失败: {reply.errorString()}")
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
    
    def show_app_detail(self, name, app_type, description, icon_url, stars=0, downloads=0, banner=""):
        """显示应用详情对话框"""
        detail_dialog = AppDetailDialog(name, app_type, description, icon_url, stars, downloads, banner, self)
        detail_dialog.exec_()


class AppDetailDialog(QDialog):
    """应用详情对话框"""
    def __init__(self, name, app_type, description, icon_url, stars=0, downloads=0, banner="", parent=None):
        super().__init__(parent)
        self.name = name
        self.app_type = app_type
        self.description = description
        self.icon_url = icon_url
        self.stars = stars
        self.downloads = downloads
        self.banner = banner
        
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
        self.changelog_content = TextEdit()
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
        
        # 相关推荐内容（暂时显示占位文本）
        recommend_content = BodyLabel("正在加载相关推荐...")
        recommend_content.setObjectName("detail_recommend_content")
        recommend_content.setWordWrap(True)
        recommend_content.setFont(QFont(load_custom_font(), 9))
        
        recommend_layout.addWidget(recommend_title)
        recommend_layout.addWidget(recommend_content)
        
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
        # 暂时显示占位文本
        self.changelog_content.setText("正在获取更新日志...")
        
        # TODO: 实现从GitHub或其他源获取更新日志的逻辑
        # 这里暂时使用模拟数据
        QTimer.singleShot(1000, self.show_mock_changelog)
    
    def show_mock_changelog(self):
        """显示模拟的更新日志"""
        mock_changelog = f"""版本 1.0.0 ({QDate.currentDate().toString('yyyy-MM-dd')})
====================================
• 初始版本发布
• 基础功能实现
• 界面优化
• 性能改进

版本 0.9.0 (2024-01-15)
====================================
• Beta版本发布
• 功能测试
• Bug修复
• 用户体验改进"""
        
        self.changelog_content.setText(mock_changelog)
    
    def install_app(self):
        """安装应用"""
        # TODO: 实现应用安装逻辑
        logger.info(f"开始安装应用: {self.name}")
        QMessageBox.information(self, "安装提示", f"正在准备安装 {self.name}...\n此功能正在开发中。")
