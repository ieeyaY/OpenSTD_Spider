import asyncio
import inspect
import sys
from functools import partial, wraps
from pathlib import Path
from tempfile import TemporaryDirectory

import aiofiles
from rich.box import SQUARE
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, DownloadColumn, Progress, TaskProgressColumn, TextColumn, TimeRemainingColumn
from rich.styled import Styled
from rich.table import Table
from typer import Argument, Option, Typer

from openstd_spider import (
    DbbaDto,
    Gb688Dto,
    HandleCaptchaError,
    HbbaDto,
    NotFoundError,
    OpenstdDto,
    StdListItem,
    StdMetaFull,
    StdSamrDto,
    StdSamrItem,
    StdSamrSearchResult,
    StdSearchResult,
    StdStatus,
    __version__,
    download_preview_img_impl,
    fuck_captcha_impl,
    reorganize_page_impl,
)
from openstd_spider.parse.gb688 import gb688_uniq_imgid
from openstd_spider.pdf import async_render_pdf_images_impl, async_render_pdf_impl
from openstd_spider.utils import is_std_code, parse_std_id, std_status2name, tid2std_kind


class AsyncTyper(Typer):
    @staticmethod
    def maybe_run_async(decorator, f):
        if inspect.iscoroutinefunction(f):

            @wraps(f)
            def runner(*args, **kwargs):
                return asyncio.run(f(*args, **kwargs))

            decorator(runner)
        else:
            decorator(f)
        return f

    def callback(self, *args, **kwargs):
        decorator = super().callback(*args, **kwargs)
        return partial(self.maybe_run_async, decorator)

    def command(self, *args, **kwargs):
        decorator = super().command(*args, **kwargs)
        return partial(self.maybe_run_async, decorator)


console = Console(highlight=False)

app = AsyncTyper(
    name="OpenSTD Spider",
    help=f"国家标准全文公开系统下载工具  Version: {__version__}",
    add_completion=False,
    pretty_exceptions_show_locals=False,
    no_args_is_help=True,
)
openstd_dto = OpenstdDto()
gb688_dto = Gb688Dto()
stdsamr_dto = StdSamrDto()
hbba_dto = HbbaDto()
dbba_dto = DbbaDto()


async def search_one(keyword: str) -> StdListItem:
    "搜索精确标准编号信息"
    result = await openstd_dto.search(
        keyword=keyword,
    )
    item_cnt = len(result.items)
    if item_cnt == 1:
        return result.items[0]
    elif item_cnt > 1:
        console.print("❌[red]查询到多条结果, 请输入完整的标准编号")
        sys.exit(-1)
    else:
        console.print("❌[red]未查询到对应标准编号的内容")
        sys.exit(-1)


async def search_samr_one(keyword: str) -> StdSamrItem | None:
    "在新平台精确检索标准编号，未命中返回 None"
    result = await stdsamr_dto.search(keyword=keyword)
    # 优先取标准号完全一致的结果(忽略空格与大小写)
    norm = keyword.replace(" ", "").upper()
    for item in result.items:
        if item.std_code.replace(" ", "").upper() == norm:
            return item
    # 退而求其次：仅一条结果时直接采用
    return result.items[0] if len(result.items) == 1 else None


async def url_or_code2std_id(target: str) -> str:
    "通过url或精确标准编号得到标准id"
    target = target.strip()
    if is_std_code(target):
        result = await search_one(target)
        std_id = result.id
    else:
        std_id = parse_std_id(target)
        if std_id is None:
            console.print(f"❌[red]目标资源id错误")
            sys.exit(-1)
    return std_id


def std_status_colored(status: StdStatus):
    "标准状态颜色显示"
    match status:
        case StdStatus.PUBLISHED:
            color = "green"
        case StdStatus.TOBEIMP:
            color = "yellow"
        case StdStatus.WITHDRAWN | StdStatus.NOTIMP:
            color = "red"
    return Styled(std_status2name(status), color)


def show_std_list(result: StdSearchResult):
    "输出标准搜索列表"
    tb = Table("序号", "标准编号", "标准名", "采标", "状态", "发布日期", "实施日期")
    tb.columns[2].overflow = "fold"
    for idx, item in enumerate(result.items):
        tb.add_row(
            str(idx),
            Styled(item.std_code, "bold green"),
            item.name_cn,
            "是" if item.is_ref else "否",
            std_status_colored(item.status),
            item.pub_date.strftime("%Y-%m-%d") if item.pub_date else "无",
            item.impl_date.strftime("%Y-%m-%d") if item.impl_date else "无",
        )
    console.print(tb)
    console.print(f"[bold green]{result.page}/{result.total_page}[/]页 共[bold green]{result.total_item}[/]条")


def samr_status_colored(status: str):
    "std.samr.gov.cn 标准状态颜色显示"
    if status == "现行":
        color = "green"
    elif status in ("即将实施", "正在征求意见", "正在起草", "正在批准"):
        color = "yellow"
    elif status in ("废止", "暂不实施"):
        color = "red"
    else:
        # 平台状态取值较多，未收录的按默认色显示，避免意外状态导致报错
        color = "white"
    return Styled(status, color)


def show_std_samr_list(result: StdSamrSearchResult):
    "输出 std.samr.gov.cn 标准搜索列表"
    tb = Table("序号", "标准编号", "标准名", "采标", "状态", "发布日期", "实施日期")
    tb.columns[2].overflow = "fold"
    for idx, item in enumerate(result.items):
        tb.add_row(
            str(idx),
            Styled(item.std_code, "bold green"),
            item.name_cn,
            "是" if item.adoption else "否",
            samr_status_colored(item.status),
            item.pub_date.strftime("%Y-%m-%d") if item.pub_date else "无",
            item.impl_date.strftime("%Y-%m-%d") if item.impl_date else "无",
        )
    console.print(tb)
    console.print(f"[bold green]{result.page}/{result.total_page}[/]页 共[bold green]{result.total_item}[/]条")


def show_std_samr_item(item: StdSamrItem):
    "输出行业/地方标准详细信息(来自 std.samr.gov.cn 检索结果)"
    tb = Table(show_header=False, show_edge=False, padding=0)
    panel = Panel(
        tb,
        title=f"[red]标准号: {item.std_code}",
        box=SQUARE,
        title_align="left",
        border_style="blue",
        expand=False,
        width=100,
    )

    tb1 = Table(show_header=False, show_edge=False, padding=0, box=None)
    tb1.add_row("中文标准名称: ", item.name_cn)
    tb1.add_row("英文标准名称: ", item.name_en or "无")
    tb1.add_row("标准状态: ", samr_status_colored(item.status))
    tb1.columns[1].overflow = "fold"
    tb.add_row(tb1)

    tb.add_section()

    tb2 = Table(show_header=False, show_edge=False, padding=0)
    tb2.add_row("[bold white]中国标准分类号（CCS）", item.ccs or "无")
    tb2.add_row("[bold white]国际标准分类号（ICS）", item.ics or "无")
    tb2.add_row("[bold white]发布日期", item.pub_date.strftime("%Y-%m-%d") if item.pub_date else "无")
    tb2.add_row("[bold white]实施日期", item.impl_date.strftime("%Y-%m-%d") if item.impl_date else "无")
    tb2.add_row("[bold white]归口单位", item.maintenance_depat or "无")
    tb2.add_row("[bold white]采标关系", item.adoption or "无")
    tb2.columns[1].overflow = "fold"
    tb.add_row(tb2)

    console.print(panel)


def show_std_meta(meta: StdMetaFull, detail: bool = True):
    "输出标准详细信息"
    if detail:
        grid = Table(show_header=False, show_edge=False, padding=0)
        panel = Panel(
            grid,
            title=f"[red]标准号: {meta.std_code}" + ("  [bold yellow]采" if meta.is_ref else ""),
            box=SQUARE,
            title_align="left",
            border_style="blue",
            expand=False,
            width=100,
        )

        tb1 = Table(show_header=False, show_edge=False, padding=0, box=None)
        tb1.add_row("中文标准名称: ", meta.name_cn)
        tb1.add_row("英文标准名称: ", meta.name_en)
        tb1.add_row("标准状态: ", std_status_colored(meta.status))
        tb1.columns[1].overflow = "fold"
        grid.add_row(tb1)

        grid.add_section()
        grid.add_row(
            (
                ("[bold green]允许" if meta.allow_preview else "[bold red]禁止")
                + "预览[/]"
                + " "
                + ("[bold green]允许" if meta.allow_download else "[bold red]禁止")
                + "下载[/]"
            )
        )
        grid.add_section()

        tb2 = Table(show_header=False, show_edge=False, padding=0)
        tb2.add_row("[bold white]中国标准分类号（CCS）", meta.ccs)
        tb2.add_row("[bold white]国际标准分类号（ICS）", meta.ics)
        tb2.add_row(
            "[bold white]发布日期",
            meta.pub_date.strftime("%Y-%m-%d") if meta.pub_date else "无",
        )
        tb2.add_row(
            "[bold white]实施日期",
            meta.impl_date.strftime("%Y-%m-%d") if meta.impl_date else "无",
        )
        tb2.add_row("[bold white]主管部门", meta.maintenance_depat)
        tb2.add_row("[bold white]归口部门", meta.centralized_depat)
        tb2.add_row("[bold white]发布单位", meta.pub_depat)
        tb2.add_row("[bold white]备注", meta.comment)
        tb2.columns[1].overflow = "fold"
        grid.add_row(tb2)

        console.print(panel)
    else:
        console.print(f"[bold green]标准编号:[/] {meta.std_code}")
        console.print(f"[bold green]中文名称:[/] {meta.name_cn}")
        console.print(f"[bold green]英文名称:[/] {meta.name_en}")


async def download_preview(std_id: str, download_path: Path):
    "预览页面方式下载"
    page_infos = await gb688_dto.get_pages(std_id)
    img_ids = gb688_uniq_imgid(page_infos)
    page_cnt = len(page_infos)
    img_cnt = len(img_ids)

    with (
        TemporaryDirectory(prefix="openstdspider") as tmp_dir,
        Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn("[progress.percentage]{task.percentage:>3.0f}%[/] {task.completed}/{task.total}"),
            TimeRemainingColumn(),
            console=console,
        ) as progress,
    ):
        tmp_dir = Path(tmp_dir)

        bar1 = progress.add_task("缓存预览图", total=img_cnt)
        await download_preview_img_impl(
            gb688_dto,
            tmp_dir,
            img_ids,
            lambda cnt: progress.update(bar1, completed=cnt),
        )
        progress.remove_task(bar1)
        console.print(f"[green]✔ [bold green]预览图缓存完毕")

        bar2 = progress.add_task("重建页面", total=page_cnt)
        await reorganize_page_impl(
            page_infos,
            tmp_dir,
            lambda cnt: progress.update(bar2, completed=cnt),
        )
        progress.remove_task(bar2)
        console.print(f"[green]✔ [bold green]页面重建完毕")

        bar3 = progress.add_task("生成PDF", total=page_cnt)
        await async_render_pdf_impl(
            page_infos,
            tmp_dir,
            download_path,
            lambda cnt: progress.update(bar3, completed=cnt),
        )
        progress.remove_task(bar3)
        console.print(f"[green]✔ [bold green]pdf生成完毕")


async def download_file(std_id: str, download_path: Path):
    "文件方式下载"
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        DownloadColumn(binary_units=True),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        bar = progress.add_task("下载PDF")
        await gb688_dto.download_pdf(
            std_id,
            download_path,
            lambda total_size, size: progress.update(bar, total=total_size, completed=size),
        )
        progress.remove_task(bar)


async def download_hbba(file_hash: str, download_path: Path):
    "行业标准全文下载(站点无PDF，逐页抓取图片后重组为PDF)"
    page_cnt = await hbba_dto.get_page_count(file_hash)
    if page_cnt <= 0:
        console.print("❌[bold red]未能获取全文页数")
        sys.exit(-1)

    with (
        TemporaryDirectory(prefix="openstdspider") as tmp_dir,
        Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn("[progress.percentage]{task.percentage:>3.0f}%[/] {task.completed}/{task.total}"),
            TimeRemainingColumn(),
            console=console,
        ) as progress,
    ):
        tmp_dir = Path(tmp_dir)

        bar1 = progress.add_task("下载页面", total=page_cnt)
        img_paths: list[Path] = []
        for no in range(page_cnt):
            img_data = await hbba_dto.get_page_img(file_hash, no)
            img_file = tmp_dir / f"P_{no}.png"
            async with aiofiles.open(img_file, "wb") as fp:
                await fp.write(img_data)
            img_paths.append(img_file)
            progress.update(bar1, completed=no + 1)
        progress.remove_task(bar1)
        console.print(f"[green]✔ [bold green]页面获取完毕")

        bar2 = progress.add_task("生成PDF", total=page_cnt)
        await async_render_pdf_images_impl(
            img_paths,
            download_path,
            lambda cnt: progress.update(bar2, completed=cnt),
        )
        progress.remove_task(bar2)
        console.print(f"[green]✔ [bold green]pdf生成完毕")


async def download_dbba(file_hash: str, download_path: Path):
    "地方标准全文下载(站点直接提供PDF)"
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        DownloadColumn(binary_units=True),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        bar = progress.add_task("下载PDF")
        await dbba_dto.download_pdf(
            file_hash,
            download_path,
            lambda total_size, size: progress.update(bar, total=total_size, completed=size),
        )
        progress.remove_task(bar)


async def download_sacinfo(item: StdSamrItem, download_path: Path):
    "行业/地方标准下载(全文由 hbba/dbba 提供，与 openstd 链路无关)"
    viewer = await stdsamr_dto.get_viewer_url(item.pid, item.tid)
    if viewer is None:
        console.print("❌[bold red]该标准未提供全文")
        sys.exit(-1)
    site, file_hash = viewer

    if download_path.is_dir():
        download_path /= item.std_code.replace("/", "") + ".pdf"

    if site == "hbba":
        await download_hbba(file_hash, download_path)
    else:
        await download_dbba(file_hash, download_path)


@app.command(name="search")
async def search(
    ps: int = Option(10, "--ps", show_default=False, help="每页条数", min=10, max=50),
    pn: int = Option(1, "-p", "--pn", show_default=False, help="页码", min=1),
    std_status: str = Option(
        "", "-s", "--status", show_default=False, help="标准状态(现行/即将实施/废止/正在征求意见/正在起草/正在批准)"
    ),
    std_nature: str = Option("", "-t", "--type", show_default=False, help="标准性质(强制性/推荐性)"),
    json_output: bool = Option(False, "-j", "--json", help="json格式输出"),
    keyword: str = Argument("", help="关键字"),
):
    "搜索 浏览标准文件列表"
    # 已由 std.samr.gov.cn（全国标准信息公共服务平台）替代：该平台是官方检索主站，
    # 覆盖范围与字段均优于 openstd 列表接口（含 ICS/CCS/英文标题/采标关系等），
    # 故下方原 openstd_dto.search 调用保留备用、不再启用。
    # 注：若要恢复，需一并恢复文件顶部的 StdType 导入、utils 的 name2std_type 导入，
    #     以及 StdStatusSelect/StdTypeSelect 枚举与 show_std_list 显示函数。
    # result = await openstd_dto.search(
    #     keyword=keyword,
    #     std_type=StdType(name2std_type(std_type.name)) if std_type else StdType.ALL,
    #     std_status=StdStatus(std_status.name) if std_status else StdStatus.ALL,
    #     ps=ps,
    #     pn=pn,
    # )
    result = await stdsamr_dto.search(
        keyword=keyword,
        status=std_status,
        nature=std_nature,
        ps=ps,
        pn=pn,
    )
    if json_output:
        sys.stdout.write(result.to_json(ensure_ascii=False, separators=(",", ":")))
    else:
        show_std_samr_list(result)


@app.command(name="info")
async def meta_info(
    json_output: bool = Option(False, "-j", "--json", help="json格式输出"),
    target: str = Argument(help="标准编号或url", show_default=False),
):
    "查询标准文件元数据"
    target = target.strip()

    # 行业/地方标准不在 openstd 覆盖范围内，元数据取自新平台检索结果
    if is_std_code(target):
        samr_item = await search_samr_one(target)
        if samr_item is not None and tid2std_kind(samr_item.tid) in ("hb", "db"):
            if json_output:
                sys.stdout.write(samr_item.to_json(ensure_ascii=False, separators=(",", ":")))
            else:
                show_std_samr_item(samr_item)
            return

    std_id = await url_or_code2std_id(target)
    try:
        meta = await openstd_dto.get_std_meta(std_id)
    except NotFoundError:
        console.print(f"❌[red]目标资源id不存在")
        sys.exit(-1)
    if json_output:
        sys.stdout.write(meta.to_json(ensure_ascii=False, separators=(",", ":")))
    else:
        show_std_meta(meta, detail=True)


@app.command(name="download")
async def download(
    detail: bool = Option(False, "-d", "--detail", help="是否展示详细元数据"),
    force_preview: bool = Option(False, "--preview", help="强制下载预览版本"),
    download_path: Path | None = Option(
        None, "-o", "--output", show_default=False, writable=True, help="下载路径或文件"
    ),
    target: str = Argument(help="标准编号或url", show_default=False),
):
    "下载标准文件PDF"
    if download_path is None:
        download_path = Path(".")

    target = target.strip()

    # 行业/地方标准不在 openstd 覆盖范围内，全文由 hbba/dbba 提供。
    # 标准类别以新平台检索结果为准(仅凭前缀无法区分，如 DB 既是地震行业标准
    # 代号也是地方标准前缀)，故先在新平台判定类别，命中行业/地方标准即走新链路。
    if is_std_code(target):
        samr_item = await search_samr_one(target)
        if samr_item is not None and tid2std_kind(samr_item.tid) in ("hb", "db"):
            show_std_samr_item(samr_item)
            console.print("[green]" + "─" * 30)
            await download_sacinfo(samr_item, download_path)
            console.print(f"[green]✔ [bold green]下载完成")
            return

    std_id = await url_or_code2std_id(target)
    try:
        meta = await openstd_dto.get_std_meta(std_id)
    except NotFoundError:
        console.print(f"❌[bold red]目标资源id不存在")
        sys.exit(-1)

    show_std_meta(meta, detail=detail)
    console.print("[green]" + "─" * 30)

    if meta.allow_download or meta.allow_preview:
        try:
            # 直接下载需先访问中转页种 token,预览方式不需要
            if meta.allow_download and not force_preview:
                await gb688_dto.prepare_download(std_id)
            await fuck_captcha_impl(gb688_dto)
        except HandleCaptchaError:
            console.print(f"[red]× [bold red]验证码识别失败")
            sys.exit(-1)
        console.print(f"[green]✔ [bold green]验证码识别成功")
    else:
        console.print(f"[red]× [bold red]资源不允许下载")
        sys.exit(-1)

    # 添加文件名
    if download_path.is_dir():
        download_path /= meta.std_code.replace("/", "") + ".pdf"

    if meta.allow_download and not force_preview:
        # 文件下载
        await download_file(std_id, download_path)
    elif meta.allow_preview:
        # 预览下载
        console.print(f"[yellow]! [bold yellow]不允许直接下载, 进行预览方式合并重组下载")
        await download_preview(std_id, download_path)

    console.print(f"[green]✔ [bold green]下载完成")
