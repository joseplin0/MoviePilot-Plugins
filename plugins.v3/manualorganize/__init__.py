"""
MoviePilot V3 手动整理插件。

插件提供“近期下载选择”和“手工地址”两种来源方式，统一复用宿主手动整理链。
"""

from typing import Any, Optional

from fastapi import Depends

from app.api.dependencies.auth import get_current_active_manage_user
from app.schemas import Response
from app.sdk.logging import logger
from app.sdk.plugin import _PluginBase

from .models import OrganizeOptionsData, OrganizeRequest, OrganizeResultData
from .service import ManualOrganizeService


class ManualOrganize(_PluginBase):
    """
    为未触发自动入库的下载提供可编辑来源地址的手动整理工作台。
    """

    plugin_name = "手动整理"
    plugin_desc = "从近期下载或手工地址触发 MoviePilot 原生手动整理，兼容远程挂载目录"
    plugin_icon = "https://raw.githubusercontent.com/joseplin0/MoviePilot-Plugins/main/icons/manual_organize.png"
    plugin_version = "1.0.0"
    plugin_author = "joseplin0"
    author_url = "https://github.com/joseplin0"
    plugin_order = 20
    auth_level = 1

    def init_plugin(self, config: Optional[dict[str, Any]] = None) -> None:
        """
        读取插件启用状态、侧栏入口和近期下载数量。

        :param config: 插件实例配置
        """
        config = config or {}
        self._enabled = bool(config.get("enabled", False))
        self._show_sidebar_nav = bool(config.get("show_sidebar_nav", True))
        try:
            history_limit = int(config.get("history_limit", 80))
        except (TypeError, ValueError):
            history_limit = 80
        self._history_limit = max(10, min(history_limit, 200))

    def get_state(self) -> bool:
        """
        返回插件当前是否启用。
        """
        return bool(getattr(self, "_enabled", False))

    @staticmethod
    def get_command() -> list[dict[str, Any]]:
        """
        当前插件不注册消息命令。
        """
        return []

    @staticmethod
    def get_render_mode() -> tuple[str, str]:
        """
        声明 Vue Federation 页面构建产物目录。
        """
        return "vue", "dist/assets"

    def get_sidebar_nav(self) -> list[dict[str, Any]]:
        """
        启用时在整理分组注册管理权限侧栏入口。
        """
        if not self.get_state() or not getattr(self, "_show_sidebar_nav", True):
            return []
        return [
            {
                "nav_key": "main",
                "title": "手动整理",
                "icon": "mdi-folder-sync-outline",
                "section": "organize",
                "permission": "manage",
                "order": 31,
            }
        ]

    def get_api(self) -> list[dict[str, Any]]:
        """
        注册工作台初始化、预览和执行接口。
        """
        dependencies = [
            Depends(get_current_active_manage_user),
            Depends(self._require_enabled),
        ]
        return [
            {
                "path": "/options",
                "endpoint": self.get_options,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "读取手动整理来源选项",
                "response_model": Response[OrganizeOptionsData],
                "dependencies": dependencies,
            },
            {
                "path": "/preview",
                "endpoint": self.preview,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "预览手动整理结果",
                "response_model": Response[OrganizeResultData],
                "dependencies": dependencies,
            },
            {
                "path": "/organize",
                "endpoint": self.organize,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "执行手动重新整理",
                "response_model": Response[OrganizeResultData],
                "dependencies": dependencies,
            },
        ]

    def get_form(self) -> tuple[list[dict], dict[str, Any]]:
        """
        返回 Federation 配置页使用的默认模型。
        """
        return [], {
            "enabled": self.get_state(),
            "show_sidebar_nav": getattr(self, "_show_sidebar_nav", True),
            "history_limit": getattr(self, "_history_limit", 80),
        }

    @staticmethod
    def get_page() -> list[dict]:
        """
        传统详情页由 Federation 页面替代。
        """
        return []

    @staticmethod
    def get_service() -> list[dict[str, Any]]:
        """
        当前插件不注册后台定时任务。
        """
        return []

    def stop_service(self) -> None:
        """
        停用插件并拒绝后续工作台请求。
        """
        self._enabled = False

    def get_options(self) -> Response[OrganizeOptionsData]:
        """
        返回近期下载记录、存储类型和有效目录规则。
        """
        try:
            data = ManualOrganizeService(self._history_limit).get_options()
            return Response(success=True, data=data)
        except Exception as error:
            logger.exception(f"读取手动整理选项失败：{error}")
            return Response(success=False, message="读取近期下载记录失败，请查看插件日志")

    def preview(
        self,
        request: OrganizeRequest,
    ) -> Response[OrganizeResultData]:
        """
        预览来源与目录规则生成的整理计划。

        :param request: 来源选择或手工地址
        :return: 预览结果
        """
        return self._execute(request=request, preview=True)

    def organize(
        self,
        request: OrganizeRequest,
    ) -> Response[OrganizeResultData]:
        """
        执行原生手动重新整理。

        :param request: 来源选择或手工地址
        :return: 逐文件执行结果
        """
        return self._execute(request=request, preview=False)

    def _execute(
        self,
        request: OrganizeRequest,
        preview: bool,
    ) -> Response[OrganizeResultData]:
        """
        统一处理业务校验、日志脱敏和错误响应。
        """
        try:
            service = ManualOrganizeService(self._history_limit)
            success, message, data = (
                service.preview(request) if preview else service.organize(request)
            )
            return Response(success=success, message=message, data=data)
        except ValueError as error:
            return Response(success=False, message=str(error))
        except Exception as error:
            logger.exception(f"手动整理执行异常：{error}")
            return Response(success=False, message="手动整理执行异常，请查看插件日志")

    def _require_enabled(self) -> None:
        """
        拒绝插件停用后的工作台请求。
        """
        if not self.get_state():
            from fastapi import HTTPException

            raise HTTPException(status_code=409, detail="插件未启用，请先启用插件")
