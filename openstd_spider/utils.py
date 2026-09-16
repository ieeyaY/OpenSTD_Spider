import re

from .schema import StdStatus, StdType

PATT_STD_ID_URL = re.compile(r"^(?:https://openstd\.samr\.gov\.cn/bzgk/(?:gb|std)/newGbInfo\?hcno=)?([0-9A-Fa-f]{32})")

# 标准编号前缀：GB 国家标准 + 各行业标准代号；地方标准另有 2 位行政区划码(如 DB11/T)
PATT_STD_CODE = re.compile(
    r"^(GB|AQ|BB|CB|CH|CJ|CY|DA|DB|DL|DZ|EJ|FZ|GA|GH|GM|HB|HG|HJ|HS|HY|JB|JC|JG|JR|JT|JY|LB|LD|LS|LY|MH|MT|MZ|"
    r"NB|NY|QB|QC|QX|RB|SB|SC|SF|SH|SJ|SL|SN|SW|SY|TD|TY|WB|WH|WJ|WM|WS|WW|XB|YB|YC|YD|YS|YY|YZ|ZY)"
    r"(\d{2})?(/[TZ]?)? \S+",
    re.I,
)


def parse_std_id(text: str) -> str | None:
    match = PATT_STD_ID_URL.search(text)
    if match is not None:
        return match.group(1)
    return None


def is_std_code(text: str) -> bool:
    return PATT_STD_CODE.search(text) is not None


def std_status2name(std_status: StdStatus) -> str | None:
    match std_status:
        case StdStatus.PUBLISHED:
            return "现行"
        case StdStatus.TOBEIMP:
            return "即将实施"
        case StdStatus.WITHDRAWN:
            return "废止"
        case StdStatus.NOTIMP:
            return "暂不实施"
        case _:
            return None


def name2std_status(name: str) -> StdStatus | None:
    match name:
        case "现行":
            return StdStatus.PUBLISHED
        case "即将实施":
            return StdStatus.TOBEIMP
        case "废止":
            return StdStatus.WITHDRAWN
        case "暂不实施":
            return StdStatus.NOTIMP
        case _:
            return None


def name2std_type(name: str) -> StdType | None:
    match name:
        case "GB":
            return StdType.GB
        case "GBT":
            return StdType.GBT
        case "GBZ":
            return StdType.GBZ
        case _:
            return None


def tid2std_kind(tid: str) -> str | None:
    """标准类别标识 -> 简类别

    gb=国家标准(全文在 openstd)、hb=行业标准(全文在 hbba)、db=地方标准(全文在 dbba)。
    未知类别返回 None。
    """
    match tid:
        case "BV_GB":
            return "gb"
        case "BV_HB":
            return "hb"
        case "BV_DB":
            return "db"
        case _:
            return None
