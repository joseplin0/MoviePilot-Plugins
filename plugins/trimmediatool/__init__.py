from pathlib import Path
from typing import Any, List, Dict, Tuple, Optional
from threading import Timer
from app.chain.media import MediaChain
from app.chain.transfer import TransferChain
from app.core.metainfo import MetaInfoPath
from app.helper.directory import DirectoryHelper
from app.helper.mediaserver import MediaServerHelper
from app.modules.trimemedia.trimemedia import TrimeMedia
from app.plugins import _PluginBase
from app.schemas import ServiceInfo,TransferInfo,MediaServerConf
from app.schemas.types import EventType
from app.log import logger
from app.core.event import eventmanager, Event
from app.core.config import settings


class TrimMediaTool(_PluginBase):
    """
    飞牛影视助手
    刷新具体媒体文件
    """
    # 插件名称
    plugin_name = "飞牛影视助手"
    # 插件描述
    plugin_desc = "入库或删除源文件自动触发飞牛扫描，支持未入库的媒体文件"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/joseplin0/MoviePilot-Plugins/main/icons/trimmedia.png"
    # 插件版本
    plugin_version = "1.1.1"
    # 插件作者
    plugin_author = "joseplin0"
    # 作者主页
    author_url = "https://github.com/joseplin0"
    # 插件配置项ID前缀
    plugin_config_prefix = "trimmediatool_"
    # 加载顺序
    plugin_order = 20
    # 可使用的用户级别
    auth_level = 1

    server_helper = None
    media_chain = None
    directory_helper = None
    transfer_chain = None

    _enabled = False
    _only_once = False
    # 媒体库目录映射
    _media_map_dirs = ""
    # 延迟扫描时间（秒）
    _delay_seconds = 10
    # 待扫描路径队列
    _scan_queue: dict[str, list[str]] = {}
    # 节流扫描方法
    _throttled_scan = None
    _del_map = {}
    # 映射目录字典
    _map_dirs: dict[str, str] = {}
    # 缓存的服务信息
    _cached_service_info: Optional[ServiceInfo] = None

    def init_plugin(self, config: dict = None):
        """
        初始化插件
        :param config: 配置信息
        """
        self.server_helper = MediaServerHelper()
        self.media_chain = MediaChain()
        self.directory_helper = DirectoryHelper()
        self.transfer_chain = TransferChain()
        
        # 清除缓存，因为配置可能发生了变化
        self._cached_service_info = None

        if not config:
            return

        self._enabled = config.get("enabled")
        self._only_once = config.get("only_once")
        self._media_map_dirs = config.get("media_map_dirs") or ""
        self._delay_seconds = config.get("delay_seconds") or 10
        # 初始化扫描队列
        self._scan_queue = {}

        if self._enabled:
            logger.info("飞牛影视插件已启用")
            # 初始化节流扫描方法 - 使用简化的防抖实现
            self._throttled_scan = self._create_debounce(
                interval=self._delay_seconds
            )(self._process_scan_queue)

            if not self._media_map_dirs:
                return
            # 查找映射目录
            logger.debug("解析媒体库目录映射配置")
            for dir_mapping in self._media_map_dirs.splitlines():
                parts = dir_mapping.split(":")
                if len(parts) == 2:
                    source_dir, target_dir = parts
                    self._map_dirs[source_dir] = target_dir
                else:
                    logger.warning(f"无效的目录映射配置: {dir_mapping}")
        pass

    @property
    def service_info(self) -> Optional[ServiceInfo]:
        """
        服务信息（带缓存）
        """
        # 如果已有缓存，直接返回
        if self._cached_service_info is not None:
            return self._cached_service_info

        # 获取媒体服务器配置
        media_config = self.get_media_config()
        logger.debug(f"获取飞牛影视配置: {media_config.name}")
        if not media_config or not media_config.name:
            logger.warning("无法获取飞牛媒体服务器配置，请检查配置")
            return None

        service: ServiceInfo = self.server_helper.get_service(media_config.name)
        if not service:
            logger.warning(f"无法获取媒体服务器 {media_config.name}，请检查配置")
            return None

        if service.instance.is_inactive():
            logger.warning(f"媒体服务器 {service.name} 未连接，请检查配置")
            return None

        # 缓存服务信息
        self._cached_service_info = service
        return service
    def get_state(self) -> bool:
        """
        获取插件状态
        """
        return self._enabled

    def get_command(self) -> List[Dict[str, Any]]:
        """
        获取插件命令
        """
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        """
        获取插件API
        """
        pass

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        获取插件配置表单
        """
        return [{
            "component": "VForm",
            "content": [
              {
                "component": "VRow",
                "content": [
                  {
                    "component": "VCol",
                    "props": {
                      "cols": 12,
                      "md": 6
                    },
                    "content": [
                      {
                        "component": "VSwitch",
                        "props": {
                          "model": "enabled",
                          "label": "启用插件"
                        }
                      },
                    ]
                  }
                ]
              },
              {
                "component": "VRow",
                "content": [
                  {
                    "component": "VCol",
                    "props": {
                      "cols": 12,
                      "md": 12
                    },
                    "content": [
                      {
                        "component": "VTextarea",
                        "props": {
                          "model": "media_map_dirs",
                          "label": "媒体库目录映射",
                          "placeholder": "/downloads:/media",
                          "hint": "每行一个映射关系，格式为：媒体库路径:飞牛路径。如果前缀一样，只要配一个就行。",
                          "persistent-hint": True
                        }
                      },
                    ]
                  },
                  {
                    "component": "VCol",
                    "props": {
                      "cols": 12,
                      "md": 12
                    },
                    "content": [
                      {
                        "component": "VAlert",
                        "props": {
                            "type": "info",
                            "variant": "tonal",
                            "text": "注意：删除源文件触发的飞牛扫描只支持自动整理"
                        },
                      },
                    ]
                  }
                ]
              },
            ]
          }
        ], {
            "enabled": False,
            "only_once": False,
            "media_map_dirs": ""
        }

    def get_page(self) -> List[dict]:
        """
        获取插件页面
        """
        pass

    @eventmanager.register(EventType.DownloadFileDeleted)
    def on_event(self, event: Event):
        """
        监听删除事件
        """
        if not self._enabled:
            return
        
        # 获取事件数据
        event_data = event.event_data
        if not event_data:
            return
            
        # 获取下载哈希
        hash = event_data.get("hash")
        src = event_data.get("src")
        if not hash or not src:
            return
        
        logger.debug(f"源文件删除,{Path(src).name}")
        
        # 先检查是否已在删除映射中
        if hash in self._del_map:
            # 将路径添加到扫描队列
            self._add_to_scan_queue(self._del_map[hash])
            return
        
        # 通过源路径获取重命名后的路径
        target_path = self.get_rename_dir(src)
        if not target_path:
            return
        fn_media_path = self.get_mp_path(str(target_path))
        if fn_media_path:
            self._del_map[hash] = fn_media_path
            # 将路径添加到扫描队列
            self._add_to_scan_queue(fn_media_path)
        return

    @eventmanager.register(EventType.TransferComplete)
    def refresh(self, event: Event):
        """
        监听整理入库，刷新飞牛媒体库
        """
        if not self._enabled:
            return
        
        logger.info("收到整理入库完成事件")
        
        if not self._media_map_dirs:
            logger.debug("未配置媒体库目录映射，跳过刷新媒体库操作")
            return

        event_info: dict = event.event_data
        if not event_info:
            return

        # 刷新媒体库
        if not self.service_info:
            return
        # 入库数据
        transferinfo: TransferInfo = event_info.get("transferinfo")
        if not transferinfo or not transferinfo.target_diritem or not transferinfo.target_diritem.path:
            return
        # /downloads/link/anime/诛仙 (2022)/
        mp_target_path = transferinfo.target_diritem.path
        fn_media_path = self.get_mp_path(mp_target_path)
        
        # 将路径添加到扫描队列
        self._add_to_scan_queue(fn_media_path)


    def _scan_media(self, library_guid: str, media_paths: List[str]) -> bool:
        """
        扫描媒体文件
        :param media_path: 媒体路径
        :return: 是否成功
        """        
        # 获取媒体库信息
        trimemedia: TrimeMedia = self.service_info.instance
        trimemedia.api.task_running()
        data = { "dir_list": media_paths }
        if (res := trimemedia.api.request(f"/mdb/scan/{library_guid}", method="post", data=data)) and res.success:
            logger.debug(f"已发送扫描请求{res}")
            if res.data:
                return True
        return False
    
    def _add_to_scan_queue(self, media_path: str):
        """
        将媒体路径添加到扫描队列（带节流）
        :param media_path: 媒体路径
        """
        path = Path(media_path)
        # 先检查路径是否已在任何媒体库的扫描队列中
        for paths in self._scan_queue.values():
            if media_path in paths:
                logger.debug(f"路径 {path.name} 已在扫描队列中，跳过添加")
                # 即使路径已在队列中，也要触发扫描以确保队列被处理
                self._throttled_scan()
                return
        
        # 获取媒体库信息
        trimemedia: TrimeMedia = self.service_info.instance
        library = trimemedia._TrimeMedia__match_library_by_path(path)
        if not library:
            logger.warning(f"路径 {path.name} 对应的媒体库未找到，跳过添加")
            self._throttled_scan()
            return
        
        # 按媒体库分组管理扫描队列
        if library.guid not in self._scan_queue:
            self._scan_queue[library.guid] = []
        
        # 将路径添加到队列
        self._scan_queue[library.guid].append(media_path)
        logger.debug(f"路径 {path.name} 添加到扫描队列，媒体库：{library.name}")
        
        # 触发节流扫描
        self._throttled_scan()
        return

    def _process_scan_queue(self):
        """
        处理扫描队列（节流执行）
        """
        if not self._scan_queue:
            logger.debug("扫描队列为空，跳过处理")
            return
        
        logger.info("扫描队列...")
        # 复制当前队列并清空
        current_queue = self._scan_queue.copy()
        self._scan_queue.clear()
        # 按媒体库分组扫描
        for library_guid, paths in current_queue.items():
            if not paths:
                continue
            try:
                logger.debug(f"扫描 {library_guid}，路径数量：{len(paths)}")
                self._scan_media(library_guid, paths)
            except Exception as e:
                logger.error(f"扫描 {library_guid} 时发生错误：{str(e)}")
        self._del_map.clear()

    def get_mp_path(self, path: str) -> str:
        """
        从映射配置中获取飞牛媒体库路径，否则返回原路径
        """
        # self.map_dirs = {"/downloads/link/anime/": "/media/anime/"}
        for mp_dir_path, fn_dir_path in self._map_dirs.items():
            if path.startswith(mp_dir_path):
                return path.replace(mp_dir_path, fn_dir_path)
        return path
    
    def get_media_config(self) -> Optional[MediaServerConf]:
        """
        获取插件媒体配置
        """
        configs = self.server_helper.get_configs()
        # 只返回 type 为 trimemedia 的配置
        for config in configs.values():
            if config.type == "trimemedia":
                return config
        return None

    def get_rename_dir(self, path: str) -> Optional[Path]:
        """
        获取重命名目录
        """
        src_path = Path(path)
        meta = MetaInfoPath(src_path)
        mediainfo = self.media_chain.recognize_media(meta)
        transfer_directory = self.directory_helper.get_dir(media=mediainfo,src_path=src_path)
        new_path = self.transfer_chain.recommend_name(meta=meta, mediainfo=mediainfo)
        media_path = DirectoryHelper.get_media_root_path(
            rename_format=settings.RENAME_FORMAT(mediainfo.type),
            rename_path=Path(new_path),
        )
        if media_path:
            new_name = media_path.name
        else:
            # fallback
            parents = Path(new_path).parents
            if len(parents) > 2:
                new_name = parents[1].name
            else:
                new_name = parents[0].name
        logger.debug(f"new_name: {new_name}")
        if transfer_directory and transfer_directory.library_path:
            return transfer_directory.library_path / Path(new_name)
        else:
            return Path(new_name)

    def get_service(self) -> List[Dict[str, Any]]:
        """
        获取插件服务
        """
        pass

    def stop_service(self):
        """
        停止插件服务
        """
        pass

    def _create_debounce(self, interval: float):
        """
        创建一个简化的防抖装饰器
        :param interval: 防抖间隔，单位秒
        """
        def decorator(func):
            timer = None

            def wrapper(*args, **kwargs):
                nonlocal timer
                
                # 取消之前的定时器
                if timer:
                    timer.cancel()
                
                # 设置新的定时器
                def delayed_execution():
                    func(*args, **kwargs)
                
                timer = Timer(interval, delayed_execution)
                timer.start()

            return wrapper
        return decorator