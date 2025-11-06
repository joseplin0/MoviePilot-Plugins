import json
from pathlib import Path
from typing import Any, List, Dict, Tuple, Optional
from app.plugins import _PluginBase
from transmission_rpc import File
from app.core.context import Context
from app.core.event import eventmanager, Event
from app.core.metainfo import MetaInfo
from app.helper.downloader import DownloaderHelper
from app.log import logger
from app.modules.transmission.transmission import Transmission
from app.schemas import ServiceInfo
from app.schemas.types import EventType


class SubscribeCheck(_PluginBase):
    """
    订阅检查插件
    主要功能：监听下载添加事件，检查订阅下载的文件是否完整
    """

    # 插件名称
    plugin_name = "订阅检查"
    # 插件描述
    plugin_desc = "监听下载添加事件，检查订阅下载的文件是否完整"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/joseplin0/MoviePilot-Plugins/main/icons/s_check.png"
    # 插件版本
    plugin_version = "1.0.1"
    # 插件作者
    plugin_author = "joseplin0"
    # 作者主页
    author_url = "https://github.com/joseplin0"
    # 插件配置项ID前缀
    plugin_config_prefix = "subscribecheck_"
    # 加载顺序
    plugin_order = 10
    # 可使用的用户级别
    auth_level = 1

    # 私有属性
    downloader_helper = None

    # 是否开启
    _enabled = False
    _onlyonce = False
    _cron = None

    def init_plugin(self, config: dict = None):
        """
        初始化插件
        """
        self.downloader_helper = DownloaderHelper()
        if not config:
            return

        self._enabled = config.get("enabled")
        self._onlyonce = config.get("only_once")
        self._cron = config.get("cron")

        if self._enabled:
            logger.info("订阅检查插件已启用")

            if self._onlyonce:
                logger.info("订阅检查服务，立即运行一次")
                # 这里可以调用一次检查逻辑

            logger.info("订阅检查插件初始化完成")

    def get_state(self) -> bool:
        """
        获取插件状态
        """
        return self._enabled

    def get_api(self) -> List[Dict[str, Any]]:
        """
        注册插件公共服务
        """
        pass

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页表单
        """
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "enabled",
                                            "label": "启用插件",
                                        },
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ], {
            "enabled": False,
        }

    def get_page(self) -> List[dict]:
        pass

    def get_command() -> List[Dict[str, Any]]:
        pass

    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册插件公共服务
        """
        pass

    @eventmanager.register(EventType.DownloadAdded)
    def handle_download_added(self, event: Event):
        """
        处理下载添加事件
        """
        if not self._enabled:
            return

        event_data = event.event_data
        if not event_data:
            return

        torrent_hash = event_data.get("hash")
        context: Context = event_data.get("context")
        downloader = event_data.get("downloader")
        episodes = list(event_data.get("episodes", []))
        username = event_data.get("username")
        source = event_data.get("source")

        logger.debug(f"接收到下载事件，来自用户: {username}, 数据: {event.event_data}")

        if not torrent_hash or not context or not context.torrent_info:
            logger.info("没有获取到有效的种子任务信息，跳过处理")
            return

        subscribe_info = self.__get_subscribe_by_source(source=source)
        if not subscribe_info:
            return

        service = self.__get_downloader_service(downloader=downloader)
        if not service:
            return

        # 检查下载任务的文件选择状态
        self._check_download_files(torrent_hash, episodes, service.instance)
        return

    def _check_download_files(self, torrent_hash: str, dl_episodes: List[str], downloader: Transmission):
        """
        检查下载文件
        """
        torrent_files = self.__torrent_get_files(downloader, torrent_hash)
        if not torrent_files:
            logger.info(f"没有在下载器中获取到 {torrent_hash} 文件列表，跳过处理")
            return
        logger.info(f"文件{torrent_hash}获取到{len(torrent_files)}个文件")
        file_ids = []
        for file in torrent_files:
            # 识别文件集
            file_meta = MetaInfo(Path(file.name).stem)
            logger.debug(f"当前文件：{file.name},{file_meta}")
            if file_meta.begin_episode:
                episode_number = file_meta.begin_episode
                logger.debug(f"文件：{file.name}，集数：{episode_number}")
            if episode_number not in dl_episodes:
                logger.debug(f"不是需要的集数")
                continue
            if not file.selected:
                file_ids.append(file.id)
                logger.info(f"{file_meta.title}未勾选下载")
        if not file_ids:
            logger.info(f"种子文件均已勾选，跳过处理")
            return
        try:
            result = downloader.set_files(torrent_hash, file_ids)
            if result:
                logger.info(f"{torrent_hash}已勾选下载")
            else:
                logger.info(f"{torrent_hash}已勾选下载失败")
        except Exception as e:
            logger.error(f"设置种子文件勾选状态失败，错误: {e}")
        return

    def __get_subscribe_by_source(self, source: str) -> Optional[Dict]:
        """
        从来源获取订阅信息
        """
        if not source or "|" not in source:
            logger.debug("未找到有效的订阅来源信息，跳过处理")
            return None

        prefix, json_data = source.split("|", 1)
        if prefix != "Subscribe":
            logger.debug(f"source 前缀不符合订阅预期值: {prefix}，跳过处理")
            return None

        try:
            subscribe_dict = json.loads(json_data)
        except Exception as e:
            logger.error(f"解析 source 数据失败，source: {json_data}, 错误: {e}")
            return None

        if subscribe_dict.get("type") != "电视剧":
            logger.info("非电视剧订阅，跳过处理")
            return None

        return subscribe_dict

    def __get_downloader_service(self, downloader: str) -> Optional[ServiceInfo]:
        """
        获取下载器服务
        """
        service = self.downloader_helper.get_service(name=downloader, type_filter="qbittorrent")
        if not service:
            logger.error(f"{downloader} 获取下载器实例失败，请检查配置")
        return service

    def __torrent_get_files(self, downloader: Transmission, torrent_hash: str) -> Optional[List[File]]:
        """
        获取下载器中的种子信息
        :param downloader: 下载器实例
        :param torrent_hashe: 种子哈希
        :return: 返回种子文件列表
        """
        if not downloader:
            logger.warning(f"获取下载器实例失败，请稍后重试")
            return None

        try:
            torrent_files = downloader.get_files(tid=torrent_hash)
        except Exception as e:
            logger.error(f"获取种子文件列表失败，错误: {e}")
            return None
        if not torrent_files:
            logger.warning(f"没有获取到种子文件列表，请稍后重试")
            return None

        return torrent_files

    def stop_service(self):
        """
        停止插件服务
        """
        pass
