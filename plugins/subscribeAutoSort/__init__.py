from datetime import datetime,timedelta
from typing import Any, List, Dict, Tuple, Optional
from app.plugins import _PluginBase
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.schemas import MediaType
from app.core.config import settings
from app.log import logger
from app.modules.themoviedb.tmdbapi import TmdbApi
from app.db.subscribe_oper import SubscribeOper
from app.db.userconfig_oper import UserConfigOper
from app.db.models.subscribe import Subscribe
from app.db.user_oper import UserOper


class SubscribeAutoSort(_PluginBase):
    # 插件名称
    plugin_name = "订阅自动排序"
    # 插件描述
    plugin_desc = "自动按上映日期对订阅进行排序"
    # 插件图标
    plugin_icon = "webhook.png"
    # 插件版本
    plugin_version = "1.0"
    # 插件作者
    plugin_author = "joseplin0"
    # 作者主页
    author_url = "https://github.com/joseplin0"
    # 插件配置项ID前缀
    plugin_config_prefix = "subscribeautosort_"
    # 加载顺序
    plugin_order = 10
    # 可使用的用户级别
    auth_level = 1

    # 配置键常量
    TV_ORDER_CONFIG_KEY = "SubscribeTvOrder"
    MOVIE_ORDER_CONFIG_KEY = "SubscribeMovieOrder"
    # 加载顺序
    plugin_order = 10
    # 可使用的用户级别
    auth_level = 1

    # 私有属性
    _enabled = False
    _onlyonce = False
    _cron = None
    _sort_order = "asc"  # 排序方向：asc-正序，desc-倒序
    _users = []  # 选择的用户列表
    subscribe_oper = None
    # 上映日期缓存 {subscribe_id: air_date}
    _air_date_cache = {}

    def init_plugin(self, config: dict = None):
        self.tmdb = TmdbApi()
        # 初始化数据库操作
        self.subscribe_oper = SubscribeOper()
        self.userConfig_oper = UserConfigOper()
        self.user_oper = UserOper()
        # 初始化插件
        if not config:
            return
        
        self._enabled = config.get("enabled")
        self._onlyonce = config.get("only_once")
        self._cron = config.get("cron")
        self._sort_order = config.get("sort_order")
        self._users = config.get("users") or []

        if self._enabled:
            logger.info(f"订阅自动排序插件已启用")
            
            if self._onlyonce:
                logger.info(f"订阅自动排序服务，立即运行一次")
                self._scheduler = BackgroundScheduler(timezone=settings.TZ)
                self._scheduler.add_job(func=self.subscribe_auto_sort, trigger='date',
                                        run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                                        name="订阅自动排序")
                # 关闭一次性开关
                self._onlyonce = False
                self.update_config({
                    "only_once": False,
                    "enabled": self._enabled,
                    "cron": self._cron,
                    "sort_order": self._sort_order,
                    "users": self._users
                })
                if self._scheduler.get_jobs():
                    # 启动服务
                    self._scheduler.print_jobs()
                    self._scheduler.start()

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """
        定义远程命令
        :return: 命令关键字、事件、描述、附带数据
        """
        return [{
            "cmd": "/subscribe_auto_sort",
            "event": "subscribe_auto_sort",
            "desc": "订阅自动排序",
            "category": "订阅",
            "data": {}
        }]

    def get_api(self) -> List[Dict[str, Any]]:
        """
        获取插件API
        [{
            "path": "/subscribe_auto_sort",
            "endpoint": self.subscribe_auto_sort,
            "methods": ["GET"],
            "summary": "订阅自动排序",
            "description": "手动触发订阅自动排序"
        }]
        """
        return [{
            "path": "/subscribe_auto_sort",
            "endpoint": self.subscribe_auto_sort,
            "methods": ["GET"],
            "summary": "订阅自动排序",
            "description": "手动触发订阅自动排序"
        }]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面，需要返回两块数据：1、页面配置；2、数据结构
        """
        all_users = self.user_oper.list()
        user_options = [{"title": user.name, "value": user.name} for user in all_users]
        
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'only_once',
                                            'label': '立即运行一次',
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VCronField',
                                        'props': {
                                            'model': 'cron',
                                            'label': '执行周期',
                                            'placeholder': '5位cron表达式，留空表示不启用定时执行',
                                        }
                                    }
                                ]
                            },
                             {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'sort_order',
                                            'label': '排序方向',
                                            'items': [
                                                {
                                                    'title': '正序（由前到后）',
                                                    'value': 'asc'
                                                },
                                                {
                                                    'title': '倒序（由后到前）',
                                                    'value': 'desc'
                                                }
                                            ]
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'users',
                                            'label': '选择用户',
                                            'multiple': True,
                                            'chips': True,
                                            'items': user_options
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                },
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal'
                                        },
                                        'content': [
                                            {
                                                'component': 'span',
                                                'text': '自动按上映日期对订阅进行排序，支持手动执行和定时执行'
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": False,
            "only_once": False,
            "sort_order": "asc",
            "cron": "",
            "users": []
        }

    def get_page(self) -> List[dict]:
        pass


    def get_user_config(self, username: str, config_key: str = TV_ORDER_CONFIG_KEY) -> List[Dict[str, str]]:
        """
        获取订阅排序配置
        :param username: 用户名
        :param config_key: 配置键名，默认为SubscribeTvOrder
        """
        return self.userConfig_oper.get(username, config_key)

    def set_user_config(self, username: str, value: List[Dict[str, str]], config_key: str = TV_ORDER_CONFIG_KEY) -> List[Dict[str, str]]:
        """
        设置订阅排序配置
        :param username: 用户名
        :param value: 配置值
        :param config_key: 配置键名，默认为SubscribeTvOrder
        """
        return self.userConfig_oper.set(username, config_key, value)

    def get_subscribe_all(self) -> List[Subscribe]:
        """
        获取所有订阅
        """
        subscribes = self.subscribe_oper.list()
        logger.info(f"获取到所有订阅{subscribes}")
        return subscribes or []

    def get_subscribe_by_user(self, username: str, mtype: str) -> List[Subscribe]:
        """
        获取用户的订阅
        管理员可以获取所有用户的订阅
        """
        # 检查用户是否为管理员
        user = self.user_oper.get_by_name(name=username)
        if user and user.is_superuser:
            # 管理员获取所有用户的订阅
            subscribes = self.subscribe_oper.list_by_type(mtype=mtype)
        else:
            # 普通用户只获取自己的订阅
            subscribes = self.subscribe_oper.list_by_username(mtype=mtype, username=username)
        logger.info(f"用户：{username} 获取到${mtype}订阅{subscribes}")
        return subscribes or []


    def sort_queue_by_user(self, username: str,mtype: str = MediaType.TV.value) -> str:
        """
        根据用户的排序配置对订阅列表进行排序
        :param username: 用户名
        :param mtype: 订阅类型
        """

        # 获取所有订阅
        subscribes = self.get_subscribe_by_user(username,mtype)
        if len(subscribes) <= 1:
            logger.info(f"用户：{username} 的订阅数量不足，无需排序")
            return

        logger.info(f"开始处理 {len(subscribes)} 个订阅的排序")
        # 获取当前的排序配置
        tv_orders = self.get_user_config(username)
        if tv_orders is None:
            # 如果获取配置失败，记录错误并返回
            return "获取订阅排序配置失败，任务终止"
        
        logger.info(f"当前排序配置: {tv_orders}")
        if not tv_orders:
            # 如果没有排序配置，根据订阅列表生成默认顺序
            logger.info("未找到现有排序配置，生成默认排序")
            tv_orders = [{"id": subscribe.id} for subscribe in subscribes]
            logger.info(f"生成的默认排序: {tv_orders}")
        
        # 使用缓存的上映日期
        subscribe_air_dates = self._air_date_cache.copy()
        subscribes_with_air_date = []
        subscribes_without_air_date = []
        
        for subscribe in subscribes:
            air_date = subscribe_air_dates.get(subscribe.id)
            if air_date:
                subscribes_with_air_date.append(subscribe)
                logger.info(f"订阅 {subscribe.name} (ID: {subscribe.id}) 的上映日期: {air_date}")
            else:
                subscribes_without_air_date.append(subscribe)
                logger.info(f"订阅 {subscribe.name} (ID: {subscribe.id}) 没有上映日期信息")
        
        # 根据上映日期对有上映日期的订阅进行排序
        reverse = self._sort_order == "desc"
        sorted_by_air_date = sorted(
            subscribes_with_air_date,
            key=lambda x: subscribe_air_dates.get(x.id),
            reverse=reverse
        )
        order_text = "正序" if self._sort_order == "asc" else "倒序"
        logger.info(f"按上映日期{order_text}排序后的订阅ID: {[s.id for s in sorted_by_air_date]}")
        
        # 创建新的排序配置：有上映日期的按指定顺序排序，没有上映日期的保持原顺序
        new_tv_orders = []
        
        # 先添加按上映日期排序的订阅
        for subscribe in sorted_by_air_date:
            if {"id": subscribe.id} not in new_tv_orders:
                new_tv_orders.append({"id": subscribe.id})
        
        # 再添加没有上映日期的订阅，保持它们在原排序中的顺序
        # 创建一个映射，用于快速查找订阅ID在原排序中的位置
        original_order_map = {}
        for idx, order in enumerate(tv_orders):
            order_id = order.get("id")
            if order_id:
                original_order_map[order_id] = idx
        
        # 对没有上映日期的订阅按原排序顺序进行排序
        sorted_without_air_date = sorted(
            subscribes_without_air_date,
            key=lambda x: original_order_map.get(x.id, float('inf')))
        
        # 添加没有上映日期的订阅
        for subscribe in sorted_without_air_date:
            if {"id": subscribe.id} not in new_tv_orders:
                new_tv_orders.append({"id": subscribe.id})
        
        logger.info(f"合并后的新排序配置: {new_tv_orders}")
        
        # 保存新的排序配置
        self.set_user_config(username, new_tv_orders)
        logger.info(f"排序配置已保存，共 {len(new_tv_orders)} 个订阅")
        
        logger.info(f"订阅自动排序任务执行完成，排序方向: {order_text}")
        return f"订阅自动排序执行完成，共处理 {len(subscribes)} 个订阅，排序方向: {order_text}"

    def subscribe_auto_sort(self) -> str:
        """
        订阅自动排序
        """
        # 预获取上映日期并缓存
        self._prefetch_air_dates()

        logger.info("开始执行订阅自动排序任务")
        
        # 确定要处理的用户列表
        if not self._users:
            logger.info("未配置用户，任务终止")
            return 
        
        logger.info(f"将处理以下用户的订阅: {self._users}")

        for username in self._users:
            logger.info(f"开始处理用户 {username} 的订阅")
            self.sort_queue_by_user(username)
            logger.info(f"用户 {username} 的订阅排序任务已完成")
        logger.info("所有用户的订阅排序任务已完成")

        return "订阅自动排序任务全部完成"

    def _prefetch_air_dates(self):
        """
        预获取所有订阅的上映日期
        """
        logger.info("开始预获取订阅上映日期")
        subscribes = self.get_subscribe_all()
        if not subscribes:
            logger.info("没有订阅需要处理")
            return
        
        logger.info(f"已有上映日期: {self._air_date_cache}")
        
        for subscribe in subscribes:
            try:
                air_date = self._get_air_date_from_api(subscribe)
                if air_date:
                    self._air_date_cache[subscribe.id] = air_date
                    logger.info(f"预获取订阅 {subscribe.name} (ID: {subscribe.id}) 的上映日期: {air_date}")
                else:
                    logger.info(f"订阅 {subscribe.name} (ID: {subscribe.id}) 没有上映日期信息")
            except Exception as e:
                logger.error(f"预获取订阅 {subscribe.name} (ID: {subscribe.id}) 的上映日期失败: {str(e)}")
        
        logger.info(f"预获取完成，共 {len(self._air_date_cache)} 个订阅的上映日期")
    
    def _get_air_date_from_api(self, subscribe: Subscribe) -> Optional[datetime]:
        """
        从API获取订阅的上映日期
        :param subscribe: 订阅信息
        :return: 上映日期，如果获取失败返回 None
        """
        try:
            logger.info(f"从API获取{subscribe.type}订阅 {subscribe.name} 的上映日期")
            if(subscribe.type == MediaType.TV.value):
                season = self.tmdb.get_tv_season_detail(subscribe.tmdbid, subscribe.season)
                logger.info(f"获取{subscribe.type}订阅 {subscribe.name} 剧集上映日期: {season.get('air_date') if season else '无'}")
                if season and season.get('air_date'):
                    return season.get('air_date')
                else:
                    logger.warning(f"{subscribe.type}订阅 {subscribe.name} (TMDB ID: {subscribe.tmdbid}) 没有剧集信息")
                    return None
            elif(subscribe.type == MediaType.MOVIE.value):
                movie = self.tmdb.get_info(MediaType.MOVIE,subscribe.tmdbid)
                logger.error(f"获取{subscribe.type}订阅 {subscribe.name} 上映日期: {movie.get('release_date') if movie else '无'}")
                if movie and movie.get('release_date'):
                    return movie.get('release_date')
                else:
                    logger.warning(f"{subscribe.type}订阅 {subscribe.name} (TMDB ID: {subscribe.tmdbid}) 没有上映日期信息")
                    return None
        except Exception as e:
            logger.error(f"获取{subscribe.type}订阅 {subscribe.name} 剧集信息失败: {str(e)}")
            return None
    

    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册插件公共服务
        [{
            "id": "subscribe_auto_sort",
            "name": "订阅自动排序服务",
            "trigger": "subscribe_auto_sort",
            "func": self.subscribe_auto_sort,
            "description": "自动按上映日期对订阅进行排序"
        }]
        """
        if self._enabled and self._cron:
            return [{
                "id": "subscribe_auto_sort",
                "name": "订阅自动排序服务",
                "trigger": CronTrigger.from_crontab(self._cron),
                "func": self.subscribe_auto_sort,
                "description": "自动按上映日期对订阅进行排序"
            }]
        return []


    def stop_service(self):
        """
        退出插件
        """
        pass
