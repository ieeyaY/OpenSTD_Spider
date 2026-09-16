import re
from datetime import date

from bs4 import BeautifulSoup

from ..schema import StdSamrItem, StdSamrSearchResult

# 分页信息在页内 JS 初始化参数中，形如 currentPage: 1, totalPages:134
PAGE_CUR_RE = re.compile(r"currentPage:\s*(\d+)")
PAGE_TOTAL_RE = re.compile(r"totalPages:\s*(\d+)")

# 详情页中的全文入口。行业标准(hbba)为 /attachment/onlineRead/{hash}，
# 地方标准(dbba)为 /portal/online/{hash}，hash 为 64 位十六进制。
VIEWER_URL_RE = re.compile(
    r"https://(?P<host>hbba|dbba)\.sacinfo\.org\.cn/(?:attachment/onlineRead|portal/online)/(?P<hash>[0-9a-f]{64})"
)

# hbba 在线预览页声明的总页数，形如 size : parseInt('64')
HBBA_SIZE_RE = re.compile(r"size\s*:\s*parseInt\(\s*['\"](\d+)['\"]\s*\)")


def stdsamr_parse_viewer_url(html_text: str) -> tuple[str, str] | None:
    """从标准详情页中提取全文入口，返回 (host, hash)。

    host 取 "hbba"（行业标准）或 "dbba"（地方标准）。无全文入口时返回 None。
    """
    match = VIEWER_URL_RE.search(html_text)
    if match is None:
        return None
    return match.group("host"), match.group("hash")


def hbba_parse_page_count(html_text: str) -> int:
    """解析 hbba 在线预览页声明的总页数，取不到时返回 0。"""
    match = HBBA_SIZE_RE.search(html_text)
    return int(match.group(1)) if match else 0


def stdsamr_parse_result(html_text: str) -> StdSamrSearchResult:
    """解析 std.samr.gov.cn 检索结果页(/search/stdPage)。

    该平台结果为服务端直出 HTML，每条对应一个 div.panel.post，按语义而非
    列下标提取：
    - 标准号：.s-title a 内 span.en-code 文本，如 "GB/T 30991-2014"
    - 名称：同一 <a> 的文本去掉标准号部分
    - 状态：.post-head 内的 span.s-status（需限定在 .post-head 内，
      页脚/分类号行还有空的 s-status，直接选 .s-status 会选错）
    - ICS/CCS：.post-flex 中标签 span 的相邻 span 文本
    - 英文标题/归口单位/采标关系：.media-inner 的 左标签->右值
    - 日期：.panel-footer time 依序前两个为发布/实施日期
    """
    items: list[StdSamrItem] = []
    html = BeautifulSoup(html_text, "lxml")

    for panel in html.select("div.panel.panel-default.post"):
        a = panel.select_one(".s-title a[tid]")
        if a is None:
            # 异常条目（无标题链接），跳过
            continue

        # 标准号由多个 <sacinfo> 片段拼成（如 <sacinfo>GB</sacinfo>/T <sacinfo>30991</sacinfo>-2014），
        # get_text(strip=True) 会把片段间的空格一并吃掉，得到 "GB/T30991-2014"，
        # 故先整体取文本再规整空白，保留 "GB/T 30991-2014" 的正确形态。
        code_node = a.select_one("span.en-code")
        std_code = " ".join(code_node.get_text().split()) if code_node else ""
        name_cn = " ".join(a.get_text().split()).replace(std_code, "").strip()

        status_node = panel.select_one(".post-head .s-status")
        status = status_node.get_text(strip=True) if status_node else ""

        # 分类号：标签 span 与其后一个 span 依次成对
        ics = ccs = ""
        flex_texts = [s.get_text(strip=True) for s in panel.select(".post-flex span")]
        for idx, text in enumerate(flex_texts):
            if idx + 1 >= len(flex_texts):
                continue
            if "ICS" in text and not ics:
                ics = flex_texts[idx + 1]
            elif "CCS" in text and not ccs:
                ccs = flex_texts[idx + 1]

        # media-inner：左侧标签 -> 右侧值
        inner: dict[str, str] = {}
        for media in panel.select(".media-inner"):
            label_node = media.select_one(".media-left")
            body_node = media.select_one(".media-body")
            if label_node is None or body_node is None:
                continue
            # 采标关系等值中含不换行空格(\xa0)且常连续出现，规整为单个空格
            inner[label_node.get_text(strip=True)] = " ".join(body_node.get_text().split())

        # 日期：发布/实施，数量不足则为 None
        times = [t.get_text(strip=True) for t in panel.select(".panel-footer time")]
        pub_date = times[0] if len(times) >= 1 else ""
        impl_date = times[1] if len(times) >= 2 else ""

        items.append(
            StdSamrItem(
                std_code=std_code,
                name_cn=name_cn,
                name_en=inner.get("英文标题", ""),
                status=status,
                ics=ics,
                ccs=ccs,
                maintenance_depat=inner.get("归口单位", ""),
                adoption=inner.get("采标关系", ""),
                pub_date=date.fromisoformat(pub_date) if pub_date else None,
                impl_date=date.fromisoformat(impl_date) if impl_date else None,
                pid=a.get("pid", ""),
                tid=a.get("tid", ""),
            )
        )

    # 总数：形如 "为您找到相关结果约 <span>1338</span> 个"
    nums_node = html.select_one(".nums span")
    total_item = int(nums_node.get_text(strip=True)) if nums_node else 0

    page = total_page = 0
    if m := PAGE_CUR_RE.search(html_text):
        page = int(m.group(1))
    if m := PAGE_TOTAL_RE.search(html_text):
        total_page = int(m.group(1))

    return StdSamrSearchResult(
        items=items,
        total_item=total_item,
        page=page,
        total_page=total_page,
    )
