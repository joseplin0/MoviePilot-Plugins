from datetime import datetime,timedelta
from typing import Any, List, Dict, Tuple, Optional
from app.plugins import _PluginBase
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.utils.http import RequestUtils
from app.core.config import settings
from app.log import logger
from app.chain.tmdb import TmdbChain
from app.db.subscribe_oper import SubscribeOper
from app.db.userconfig_oper import UserConfigOper
from app.db.models.subscribe import Subscribe

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
    # 加载顺序
    plugin_order = 10
    # 可使用的用户级别
    auth_level = 1

    # 私有属性
    _enabled = False
    _onlyonce = False
    _cron = None
    _sort_order = "asc"  # 排序方向：asc-正序，desc-倒序
    subscribe_oper = None

    def init_plugin(self, config: dict = None):
        self.tmdb_chain = TmdbChain()
        # 初始化数据库操作
        self.subscribe_oper = SubscribeOper()
        self.userConfig_oper = UserConfigOper()
        # 初始化插件
        if not config:
            return
        
        self._enabled = config.get("enabled")
        self._onlyonce = config.get("only_once")
        self._cron = config.get("cron")
        self._sort_order = config.get("sort_order", "asc")

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
                    "sort_order": self._sort_order
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
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'cron',
                                            'label': '执行周期',
                                            'placeholder': '5位cron表达式，留空自动'
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
            "cron": ""
        }

    def get_page(self) -> List[dict]:
        pass

    def _call_user_config_api(self, method: str = "GET", data: Any = None, config_key: str = TV_ORDER_CONFIG_KEY) -> List[Dict[str,str]]:
        """
        调用用户配置API
        :param method: HTTP方法，GET或POST
        :param data: 请求数据，仅POST时使用
        :param config_key: 配置键名，默认为 SubscribeTvOrder
        :return: 配置数据
        """
        # 构建API URL
        api_url = f"http://localhost:{settings.PORT}{settings.API_V1_STR}/user/config/{config_key}"
        logger.debug(f"调用用户配置API: {api_url}",method)
        request = RequestUtils()
        # 根据方法发送请求
        if method.upper() == "GET":
            response = request.get_res(api_url)
        else:
            response = request.post_res(api_url, json=data)
        
        if response and response.status_code == 200:
            result = response.json()
            if result.get("success"):
                if method.upper() == "GET":
                    # GET请求返回配置数据
                    if "data" in result and "value" in result["data"]:
                        logger.info(f"通过接口成功获取订阅排序配置: {config_key}")
                        # 如果 value 是 null，则返回 []
                        return result["data"]["value"] or []
                    else:
                        # POST请求返回成功状态
                        logger.info(f"订阅排序配置已通过接口更新: {config_key}")
                        return data
            else:
                logger.error(f"接口返回失败: {result}")
                return None
        else:
            logger.error(f"通过接口操作订阅排序配置失败: {response}")
            return None

    def get_user_config(self, config_key: str = TV_ORDER_CONFIG_KEY) -> List[Dict[str,str]]:
        """
        获取订阅排序配置
        :param config_key: 配置键名，默认为SubscribeTvOrder
        """
        return self._call_user_config_api("GET", config_key=config_key)
    def set_user_config(self, value: List[Dict[str,str]], config_key: str = TV_ORDER_CONFIG_KEY) -> List[Dict[str,str]]:
        """
        设置订阅排序配置
        :param value: 配置值
        :param config_key: 配置键名，默认为SubscribeTvOrder
        """
        return self._call_user_config_api("POST", value, config_key=config_key)

    def get_subscribe_movies(self):
        """
        获取所有电影订阅
        """
        # 获取电影订阅
        subscribes = self.subscribe_oper.list_by_type(mtype="电影")
        return subscribes or []

    def get_subscribe_tvs(self) -> List[Subscribe]:
        """
        获取所有电视剧订阅
        """
        # 获取电视剧订阅
        subscribes = self.subscribe_oper.list_by_type(mtype="电视剧")
        logger.info(f"获取到电视剧订阅{subscribes}")
        return subscribes or []

    def subscribe_auto_sort(self) -> str:
        """
        订阅自动排序
        """
        logger.info("开始执行订阅自动排序任务")
        
        # 获取所有订阅
        subscribes = self.get_subscribe_tvs()

        if len(subscribes) <= 1:
            logger.info("请添加更多订阅！")
            return
        
        logger.info(f"开始处理 {len(subscribes)} 个订阅的排序")
        
        # 获取当前的排序配置
        tv_orders = self.get_user_config()
        
        # if tv_orders is None:
        #     # 如果获取配置失败，记录错误并返回
        #     return "获取订阅排序配置失败，任务终止"
        
        logger.info(f"当前排序配置: {tv_orders}")
        if not tv_orders:
            # 如果没有排序配置，根据订阅列表生成默认顺序
            logger.info("未找到现有排序配置，生成默认排序")
            tv_orders = [{"id": subscribe.id} for subscribe in subscribes]
            logger.info(f"生成的默认排序: {tv_orders}")
        
        # 获取每个订阅的上映日期
        subscribe_air_dates = {}
        subscribes_with_air_date = []
        subscribes_without_air_date = []
        
        for subscribe in subscribes:
            try:
                air_date = self.get_tv_air_date(subscribe)
                if air_date:
                    subscribe_air_dates[subscribe.id] = air_date
                    subscribes_with_air_date.append(subscribe)
                    logger.info(f"订阅 {subscribe.name} (ID: {subscribe.id}) 的上映日期: {air_date}")
                else:
                    subscribes_without_air_date.append(subscribe)
                    logger.info(f"订阅 {subscribe.name} (ID: {subscribe.id}) 没有上映日期信息")
            except Exception as e:
                logger.error(f"获取订阅 {subscribe.name} (ID: {subscribe.id}) 的上映日期失败: {str(e)}")
                subscribes_without_air_date.append(subscribe)
        
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
        for order in tv_orders:
            order_id = order.get("id")
            # 只添加没有上映日期的订阅
            if order_id and any(sub.id == order_id for sub in subscribes_without_air_date):
                if order not in new_tv_orders:
                    new_tv_orders.append(order)
        
        logger.info(f"合并后的新排序配置: {new_tv_orders}")
        
        # 保存新的排序配置
        self.set_user_config(new_tv_orders)
        logger.info(f"排序配置已保存，共 {len(new_tv_orders)} 个订阅")
        
        logger.info(f"订阅自动排序任务执行完成，排序方向: {order_text}")
        return f"订阅自动排序执行完成，共处理 {len(subscribes)} 个订阅，排序方向: {order_text}"
    
    def get_tv_air_date(self, subscribe: Subscribe) -> Optional[datetime]:
        """
        获取电视剧订阅的上映日期
        :param subscribe: 订阅信息
        :return: 上映日期，如果获取失败返回 None
        """
        try:
            episodes = self.tmdb_chain.tmdb_episodes(subscribe.tmdbid, subscribe.season)
            if episodes and len(episodes) > 0:
                return episodes[0].air_date
            else:
                logger.warning(f"订阅 {subscribe.name} (TMDB ID: {subscribe.tmdbid}) 没有剧集信息")
                return None
        except Exception as e:
            logger.error(f"获取订阅 {subscribe.name} 剧集信息失败: {str(e)}")
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
        elif self._enabled:
            return [{
                "id": "subscribe_auto_sort",
                "name": "订阅自动排序服务",
                "trigger": CronTrigger.from_crontab("0 0 */7 * *"),
                "func": self.subscribe_auto_sort,
                "description": "自动按上映日期对订阅进行排序"
            }]
        return []


    def stop_service(self):
        """
        退出插件
        """
        pass
