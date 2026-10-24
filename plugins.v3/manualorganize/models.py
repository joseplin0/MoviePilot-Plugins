"""
手动整理插件的请求、选项和执行结果模型。
"""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StorageOption(BaseModel):
    """
    页面可选的源存储类型。
    """

    value: str = Field(description="提交给整理链的存储标识")
    title: str = Field(description="页面显示名称")
    hint: str = Field(default="", description="该存储的路径填写说明")


class SourceOption(BaseModel):
    """
    从近期下载历史生成的远程挂载友好来源选项。
    """

    history_id: int = Field(description="下载历史记录标识")
    title: str = Field(description="媒体标题")
    path: str = Field(description="下载记录保存的文件或目录路径")
    storage: str = Field(default="local", description="源存储类型")
    item_type: Literal["file", "dir"] = Field(description="来源是单文件还是目录")
    date: Optional[str] = Field(default=None, description="下载记录时间")
    media_type: Optional[str] = Field(default=None, description="下载记录中的媒体类型")
    organized: bool = Field(default=False, description="该源路径是否已有成功整理记录")


class DirectoryRootOption(BaseModel):
    """
    MoviePilot 中可用于手动整理的目录规则摘要。
    """

    name: str = Field(description="目录规则名称")
    storage: str = Field(default="local", description="下载目录存储类型")
    path: str = Field(description="下载目录根路径")
    target_storage: str = Field(default="local", description="媒体库目录存储类型")
    target_path: str = Field(description="媒体库根路径")


class OrganizeOptionsData(BaseModel):
    """
    手动整理工作台初始化数据。
    """

    sources: list[SourceOption] = Field(default_factory=list, description="近期下载历史来源")
    storages: list[StorageOption] = Field(default_factory=list, description="可填写地址的存储类型")
    directory_roots: list[DirectoryRootOption] = Field(default_factory=list, description="当前启用的整理目录规则")
    history_limit: int = Field(description="本次返回的近期下载记录上限")


class OrganizeRequest(BaseModel):
    """
    手动整理请求。

    选择近期下载时只接受 history_id；手工地址模式要求同时给出存储、路径和条目类型。
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    mode: Literal["history", "path"] = Field(description="来源方式：近期下载或手工地址")
    history_id: Optional[int] = Field(default=None, ge=1, description="近期下载历史记录标识")
    storage: str = Field(default="local", description="手工地址所属存储")
    path: Optional[str] = Field(default=None, min_length=1, description="手工输入的文件或目录地址")
    item_type: Literal["file", "dir"] = Field(default="dir", description="手工地址是文件还是目录")

    @model_validator(mode="after")
    def validate_source(self) -> "OrganizeRequest":
        """
        保证两种来源方式只携带各自必需的定位字段。
        """
        if self.mode == "history":
            if self.history_id is None:
                raise ValueError("请选择一条近期下载记录")
            return self
        if not self.path:
            raise ValueError("请输入要整理的文件或目录地址")
        return self


class OrganizeItemResult(BaseModel):
    """
    单个媒体文件的预览或执行结果。
    """

    source: Optional[str] = Field(default=None, description="源文件路径")
    target: Optional[str] = Field(default=None, description="目标文件路径")
    target_dir: Optional[str] = Field(default=None, description="目标目录")
    state: Optional[str] = Field(default=None, description="整理状态，实际入库只以 completed 为准")
    success: Optional[bool] = Field(default=None, description="请求是否被接收或执行成功")
    message: Optional[str] = Field(default=None, description="结果说明")
    failure_stage: Optional[str] = Field(default=None, description="失败阶段")
    recovery_action: Optional[str] = Field(default=None, description="建议的恢复操作")
    overwrite_skipped: bool = Field(default=False, description="是否因覆盖策略跳过")
    title: Optional[str] = Field(default=None, description="识别到的媒体标题")
    type: Optional[str] = Field(default=None, description="识别到的媒体类型")
    season: Optional[int] = Field(default=None, description="识别到的季号")


class OrganizeResultData(BaseModel):
    """
    一次手动整理预览或执行的汇总结果。
    """

    preview: bool = Field(description="是否为只读预览")
    selection_strategy: str = Field(description="来源文件发现方式")
    source_storage: str = Field(description="源存储类型")
    source_path: str = Field(description="源文件或目录路径")
    source_type: Literal["file", "dir"] = Field(description="源条目类型")
    target_storage: str = Field(description="目标存储类型")
    target_path: str = Field(description="由目录规则精确匹配的媒体库根路径")
    total: int = Field(default=0, description="结果条目总数")
    preview_success: int = Field(default=0, description="预览成功生成目标路径的数量")
    completed: int = Field(default=0, description="已确认完成入库的数量")
    accepted: int = Field(default=0, description="仅被后台接收的数量")
    failed: int = Field(default=0, description="执行失败的数量")
    skipped: int = Field(default=0, description="跳过的数量")
    retry_wait: int = Field(default=0, description="等待后台重试的数量")
    manual_review: int = Field(default=0, description="等待人工复核的数量")
    message: str = Field(default="", description="整理链返回的汇总说明")
    items: list[OrganizeItemResult] = Field(default_factory=list, description="逐文件结果")
