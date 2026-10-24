"""
手动整理插件的来源解析、目录匹配和整理链调用。
"""

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.application.directory import DirectoryHelper
from app.chain.transfer import TransferChain
from app.db.oper.downloadhistory import DownloadHistoryOper
from app.schemas.file import FileItem, FileURI
from app.schemas.query import DownloadHistorySnapshot
from app.schemas.system import TransferDirectoryConf
from app.schemas.types import MediaType, StorageSchema
from app.sdk.config import settings
from app.sdk.logging import logger
from app.sdk.queries import (
    get_download_history,
    list_download_history,
    list_transfer_history,
)

from .models import (
    DirectoryRootOption,
    OrganizeItemResult,
    OrganizeOptionsData,
    OrganizeRequest,
    OrganizeResultData,
    SourceOption,
    StorageOption,
)


@dataclass(frozen=True)
class ResolvedSource:
    """
    已解析且可交给整理链的来源上下文。

    :param fileitem: 作为整理根节点的文件或目录
    :param selected_fileitems: 下载历史中已知的媒体文件；存在时避免列出远程目录
    :param history: 近期下载来源对应的只读历史快照
    :param selection_strategy: 页面展示的来源发现方式说明
    """

    fileitem: FileItem
    selected_fileitems: Optional[list[FileItem]]
    history: Optional[DownloadHistorySnapshot]
    selection_strategy: str


class ManualOrganizeService:
    """
    复用 MoviePilot 手动整理链并提供不依赖目录浏览的近期下载选择。
    """

    _STORAGE_LABELS = {
        "local": ("本地 / 挂载目录", "本地磁盘、NFS、SMB 或 rclone 挂载到容器后的路径"),
        "alipan": ("阿里云盘", "填写云盘内部路径"),
        "u115": ("115 网盘", "填写网盘内部路径"),
        "rclone": ("Rclone 存储", "填写 Rclone 存储内部路径"),
        "alist": ("OpenList", "填写 OpenList 内部路径"),
        "alistgo": ("AList", "填写 AList 内部路径"),
        "smb": ("SMB 共享", "填写共享内部路径，不是宿主机挂载路径"),
    }

    def __init__(self, history_limit: int = 80) -> None:
        """
        保存工作台近期下载记录上限。

        :param history_limit: 页面最多返回的下载历史数量
        """
        self._history_limit = max(10, min(int(history_limit), 200))
        self._directory_helper = DirectoryHelper()

    def get_options(self) -> OrganizeOptionsData:
        """
        返回近期下载、存储类型和当前目录规则。
        """
        download_page = list_download_history(
            page={
                "page": 1,
                "count": self._history_limit,
                "sort": {"field": "date", "direction": "desc"},
            }
        )
        transfer_page = list_transfer_history(
            page={
                "page": 1,
                "count": 200,
                "sort": {"field": "date", "direction": "desc"},
            }
        )
        organized_paths = {
            self._path_key(item.src_storage or "local", item.src)
            for item in transfer_page.items
            if item.status and item.src
        }

        sources: list[SourceOption] = []
        for history in download_page.items:
            if not history.path:
                continue
            fileitem = self._history_root_fileitem(history)
            sources.append(
                SourceOption(
                    history_id=history.id,
                    title=self._history_title(history),
                    path=fileitem.path or history.path,
                    storage=fileitem.storage or "local",
                    item_type=fileitem.type or "dir",
                    date=history.date,
                    media_type=history.type,
                    organized=self._path_key(fileitem.storage, fileitem.path) in organized_paths,
                )
            )

        roots = [
            DirectoryRootOption(
                name=directory.name or directory.download_path or "未命名目录",
                storage=directory.storage or "local",
                path=directory.download_path,
                target_storage=directory.library_storage or "local",
                target_path=directory.library_path,
            )
            for directory in self._directory_helper.get_download_dirs()
            if directory.download_path
            and directory.library_path
            and directory.monitor_type
        ]
        storages = [
            StorageOption(
                value=storage.value,
                title=self._STORAGE_LABELS.get(storage.value, (storage.value, ""))[0],
                hint=self._STORAGE_LABELS.get(storage.value, (storage.value, ""))[1],
            )
            for storage in StorageSchema
        ]
        return OrganizeOptionsData(
            sources=sources,
            storages=storages,
            directory_roots=roots,
            history_limit=self._history_limit,
        )

    def preview(self, request: OrganizeRequest) -> tuple[bool, str, OrganizeResultData]:
        """
        同步预览来源将使用的目标目录和逐文件结果。

        :param request: 页面提交的来源定位信息
        :return: 是否成功、提示文案和预览数据
        """
        return self._run(request=request, preview=True)

    def organize(self, request: OrganizeRequest) -> tuple[bool, str, OrganizeResultData]:
        """
        同步执行重新整理，完成状态只认逐项 state=completed。

        :param request: 页面提交的来源定位信息
        :return: 是否成功、提示文案和执行数据
        """
        return self._run(request=request, preview=False)

    def _run(
        self,
        request: OrganizeRequest,
        preview: bool,
    ) -> tuple[bool, str, OrganizeResultData]:
        """
        解析来源、锁定目标目录并调用宿主手动整理链。
        """
        source = self._resolve_source(request)
        target = self._resolve_target(source.fileitem)
        target_path = str(target.library_path)
        target_storage = target.library_storage or "local"
        history = source.history
        media_type = self._media_type(history.type if history else None)
        media_source = history.media_source if history and history.media_source and history.media_id else None
        media_id = history.media_id if media_source and history else None

        success, payload = TransferChain().manual_transfer(
            fileitem=source.fileitem,
            selected_fileitems=source.selected_fileitems,
            target_storage=target_storage,
            target_path=Path(target_path),
            media_source=media_source,
            media_id=media_id,
            mtype=media_type,
            episode_group=history.episode_group if history else None,
            transfer_type=target.transfer_type,
            scrape=bool(target.scraping),
            library_type_folder=bool(target.library_type_folder),
            library_category_folder=bool(target.library_category_folder),
            background=False,
            downloader=history.downloader if history else None,
            download_hash=history.download_hash if history else None,
            preview=preview,
            sync_extra_files=source.selected_fileitems is None,
            reorganize=True,
            music_type=history.music_type if history else None,
            report_results=True,
            skip_success=False,
        )
        result_payload = payload if isinstance(payload, dict) else {}
        raw_items = result_payload.get("items")
        items = [
            OrganizeItemResult.model_validate(item)
            for item in raw_items
            if isinstance(item, dict)
        ] if isinstance(raw_items, list) else []
        states = Counter(item.state for item in items if item.state)
        message = str(result_payload.get("message") or (payload if isinstance(payload, str) else ""))
        data = OrganizeResultData(
            preview=preview,
            selection_strategy=source.selection_strategy,
            source_storage=source.fileitem.storage or "local",
            source_path=source.fileitem.path or "",
            source_type=source.fileitem.type or "dir",
            target_storage=target_storage,
            target_path=target_path,
            total=len(items),
            preview_success=sum(1 for item in items if preview and item.success),
            completed=states["completed"],
            accepted=states["accepted"],
            failed=states["failed"] + sum(
                1 for item in items if item.state is None and item.success is False
            ),
            skipped=states["skipped"],
            retry_wait=states["retry_wait"],
            manual_review=states["manual_review"],
            message=message,
            items=items,
        )
        if success:
            return True, message, data
        return False, message or "手动整理未完成，请查看逐文件结果", data

    def _resolve_source(self, request: OrganizeRequest) -> ResolvedSource:
        """
        按近期下载或手工地址构造整理根节点。
        """
        if request.mode == "path":
            fileitem = self._manual_fileitem(request)
            return ResolvedSource(
                fileitem=fileitem,
                selected_fileitems=None,
                history=None,
                selection_strategy=(
                    "精确文件地址，不列目录"
                    if fileitem.type == "file"
                    else "手工目录地址，由 MoviePilot 扫描目录"
                ),
            )

        history = get_download_history(request.history_id or 0)
        if not history or not history.path:
            raise ValueError("近期下载记录不存在或缺少保存路径，请刷新后重试")
        root = self._history_root_fileitem(history)
        selected = self._history_fileitems(history, root.storage or "local")
        if root.type == "dir" and not selected:
            raise ValueError(
                "该下载记录没有可用的文件清单，为避免远程目录卡住，请改用“输入地址”并填写准确媒体文件"
            )
        return ResolvedSource(
            fileitem=root,
            selected_fileitems=selected or None,
            history=history,
            selection_strategy=(
                f"下载历史中的 {len(selected)} 个已知媒体文件，不列远程目录"
                if selected
                else "下载历史中的单个媒体文件，不列远程目录"
            ),
        )

    def _resolve_target(self, fileitem: FileItem) -> TransferDirectoryConf:
        """
        按源路径匹配目录规则并返回必须原值回传的媒体库根路径。
        """
        if not fileitem.path:
            raise ValueError("来源路径为空")
        directory = self._directory_helper.get_dir(
            media=None,
            storage=fileitem.storage or "local",
            src_path=Path(fileitem.path),
        )
        if not directory or not directory.library_path:
            raise ValueError(
                "来源地址未匹配到已启用监控的下载目录，请先在“设置 → 存储 & 目录”配置对应规则"
            )
        return directory

    def _manual_fileitem(self, request: OrganizeRequest) -> FileItem:
        """
        解析带存储前缀或独立存储选择的手工地址。
        """
        raw_path = str(request.path or "").strip()
        parsed = FileURI.from_uri(raw_path)
        has_storage_prefix = any(
            raw_path.startswith(f"{storage.value}:") for storage in StorageSchema
        )
        storage = parsed.storage if has_storage_prefix else request.storage
        path = parsed.path if has_storage_prefix else Path(raw_path).as_posix()
        if storage != "local" and path and not path.startswith("/"):
            path = f"/{path}"
        return FileItem(
            storage=storage,
            path=path,
            type=request.item_type,
            name=Path(path).name or path,
        )

    def _history_root_fileitem(self, history: DownloadHistorySnapshot) -> FileItem:
        """
        从下载历史路径推断源存储和根条目类型，不访问文件系统。
        """
        parsed = FileURI.from_uri(history.path or "")
        storage = parsed.storage or "local"
        path = parsed.path or history.path or ""
        if storage == "local":
            matching_directory = self._match_download_root(path)
            if matching_directory:
                storage = matching_directory.storage or "local"
        extensions = {
            str(extension).lower()
            for extension in [*settings.RMT_MEDIAEXT, *settings.RMT_AUDIOEXT]
        }
        item_type = "file" if Path(path).suffix.lower() in extensions else "dir"
        return FileItem(
            storage=storage,
            path=path,
            type=item_type,
            name=Path(path).name or path,
        )

    def _history_fileitems(
        self,
        history: DownloadHistorySnapshot,
        storage: str,
    ) -> list[FileItem]:
        """
        读取下载历史已知媒体文件，避免为远程挂载目录执行全量列目录。
        """
        if not history.download_hash:
            return []
        try:
            records = DownloadHistoryOper().get_files_by_hash(
                history.download_hash,
                state=1,
            )
        except Exception as error:
            logger.warning(f"读取下载文件清单失败，将回退为目录扫描：{error}")
            return []
        fileitems: list[FileItem] = []
        seen_paths = set()
        for record in records:
            fullpath = str(getattr(record, "fullpath", "") or "").strip()
            if not fullpath or fullpath in seen_paths:
                continue
            seen_paths.add(fullpath)
            parsed = FileURI.from_uri(fullpath)
            fileitems.append(
                FileItem(
                    storage=parsed.storage if parsed.storage != "local" else storage,
                    path=parsed.path,
                    type="file",
                    name=Path(parsed.path or fullpath).name,
                )
            )
        return fileitems

    def _match_download_root(self, path: str) -> Optional[TransferDirectoryConf]:
        """
        按最深下载根路径推断未带 URI 前缀的历史记录所属存储。
        """
        source = Path(path)
        matches = []
        for index, directory in enumerate(self._directory_helper.get_download_dirs()):
            if not directory.download_path:
                continue
            root = Path(directory.download_path)
            try:
                if source == root or source.is_relative_to(root):
                    matches.append((-len(root.parts), directory.priority or 0, index, directory))
            except (TypeError, ValueError):
                continue
        return min(matches, key=lambda item: item[:3])[3] if matches else None

    @staticmethod
    def _history_title(history: DownloadHistorySnapshot) -> str:
        """
        生成近期下载下拉框的简短标题。
        """
        title = history.title or history.torrent_name or Path(history.path or "").name
        if history.year:
            title = f"{title} ({history.year})"
        episode = history.episodes or history.seasons
        return f"{title} {episode}".strip() if episode else title

    @staticmethod
    def _media_type(value: Optional[str]) -> Optional[MediaType]:
        """
        把下载历史中的中英文类型转换为宿主枚举。
        """
        if not value:
            return None
        try:
            return MediaType(value)
        except ValueError:
            return MediaType.from_agent(value)

    @staticmethod
    def _path_key(storage: Optional[str], path: Optional[str]) -> tuple[str, str]:
        """
        生成存储与路径的稳定比较键。
        """
        return storage or "local", Path(path or "").as_posix()
