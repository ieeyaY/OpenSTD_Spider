from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from dataclasses_json import config, dataclass_json


@dataclass
class Gb688Block:
    x: int
    y: int
    img_x: int
    img_y: int


@dataclass
class Gb688Page:
    no: int
    img_id: str
    h: int
    w: int
    blocks: list[Gb688Block]


class StdStatus(Enum):
    ALL = ""
    PUBLISHED = "PUBLISHED"
    TOBEIMP = "TOBEIMP"
    WITHDRAWN = "WITHDRAWN"
    NOTIMP = "NOTIMP"


class StdType(Enum):
    ALL = 0
    GB = 1
    GBT = 2
    GBZ = 3


@dataclass_json
@dataclass
class StdMeta:
    std_code: str
    is_ref: bool
    name_cn: str
    status: StdStatus = field(metadata=config(encoder=lambda x: x.value))
    pub_date: None | date = field(metadata=config(encoder=lambda x: x.isoformat() if x else None))
    impl_date: None | date = field(metadata=config(encoder=lambda x: x.isoformat() if x else None))


@dataclass
class StdMetaFull(StdMeta):
    name_en: str
    allow_preview: bool
    allow_download: bool
    ccs: str
    ics: str
    maintenance_depat: str
    centralized_depat: str
    pub_depat: str
    comment: str


@dataclass
class StdListItem(StdMeta):
    id: str


@dataclass_json
@dataclass
class StdSearchResult:
    items: list[StdListItem]
    total_item: int
    page: int
    total_page: int


@dataclass_json
@dataclass
class StdSamrItem:
    """std.samr.gov.cn（全国标准信息公共服务平台）检索结果条目。

    该平台字段比 openstd 更丰富，且标准状态取值超出 StdStatus 枚举范围
    （如 正在征求意见/正在起草/正在批准），故状态用字符串原样保存，
    避免出现未知状态时抛错。
    """

    std_code: str
    name_cn: str
    name_en: str
    status: str
    ics: str
    ccs: str
    maintenance_depat: str
    adoption: str
    pub_date: None | date = field(metadata=config(encoder=lambda x: x.isoformat() if x else None))
    impl_date: None | date = field(metadata=config(encoder=lambda x: x.isoformat() if x else None))
    pid: str = ""
    # 标准类别标识：BV_GB 国家标准 / BV_HB 行业标准 / BV_DB 地方标准，
    # 决定详情页路由(详情页类型)与全文来源站点
    tid: str = ""


@dataclass_json
@dataclass
class StdSamrSearchResult:
    items: list[StdSamrItem]
    total_item: int
    page: int
    total_page: int
