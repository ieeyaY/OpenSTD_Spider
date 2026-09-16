# OpenSTD_Spider

国家标准 / 行业标准 / 地方标准 检索与下载工具

OpenSTD_Spider 是一个用于下载国家标准委公开标准文件的工具，集成搜索、元数据查询、PDF 下载三个功能，可以使用 CLI 调用，也可作为库通过 API 接口供其他程序调用。

目前支持**国家标准**、**行业标准**、**地方标准**三类标准文件，数据分别来自以下平台：

| 标准类别 | 检索来源 | 全文来源 |
| --- | --- | --- |
| 国家标准 | [全国标准信息公共服务平台](https://std.samr.gov.cn/) | [国家标准全文公开系统](https://openstd.samr.gov.cn/bzgk/gb/) |
| 行业标准 | [全国标准信息公共服务平台](https://std.samr.gov.cn/) | [行业标准信息服务平台](https://hbba.sacinfo.org.cn/) |
| 地方标准 | [全国标准信息公共服务平台](https://std.samr.gov.cn/) | [地方标准信息服务平台](https://dbba.sacinfo.org.cn/) |

本项目下载及输出的内容均从上述网站获取，使用其输出内容必须遵守相关规定，以及国家标准和国际标准的版权。

## 🚀Quick Start

需要 Python 版本 >= 3.10

```bash
pip install openstd_spider
```

也可以通过[源代码构建](#Building)

## 💻Usage

### 搜索公开标准列表

使用方式为子命令 `openstd_spider search`

```
Usage: openstd_spider search [OPTIONS] [KEYWORD]

 搜索 浏览标准文件列表

 Arguments
 keyword      [KEYWORD]  关键字

 Options
 --ps              INTEGER RANGE [10<=x<=50]  每页条数
 --pn      -p      INTEGER RANGE [x>=1]       页码
 --status  -s      TEXT                       标准状态(现行/即将实施/废止/正在征求意见/正在起草/正在批准)
 --type    -t      TEXT                       标准性质(强制性/推荐性)
 --json    -j                                 json格式输出
 --help                                       Show this message and exit.
```

> [!NOTE]
> 检索已由 [全国标准信息公共服务平台](https://std.samr.gov.cn/)（`std.samr.gov.cn`）提供，该平台是官方检索主站，同时覆盖国家标准、行业标准、地方标准，且字段比全文公开系统更丰富（含 ICS/CCS、英文标题、归口单位、采标关系等）。
>
> 因此 `-s`/`-t` 由原先的枚举改为自由文本：`-s` 对应标准状态、`-t` 对应标准性质，取值超出上述范围时结果可能为空。

浏览最新公开的标准文件

```bash
openstd_spider search
```

也可以通过关键字或标准编号搜索

```bash
# 搜索标准编号
openstd_spider search 'GB 18030'
# 搜索关键字
openstd_spider search '电动自行车'
```

输出的表格底部会显示索引信息，可使用`-p`参数翻页

### 查询标准元数据

使用方式为子命令 `openstd_spider info`

```
Usage: openstd_spider info [OPTIONS] TARGET                              
                                                                              
 查询标准文件元数据

 Arguments
 *    target      TEXT  标准编号或url [required]
 
 Options
 --json  -j        json格式输出
 --help            Show this message and exit.
```

元数据包含标准编号、中英文名称、分类编号、发布及实施日期、主管及归口单位等。

国家标准与行业/地方标准的元数据来源不同（分别取自全文公开系统与全国标准信息公共服务平台），因此展示的字段略有差异，行业/地方标准额外包含 ICS/CCS、归口单位、采标关系等。

通过精确的标准编号（非精确的标准编号最多一个匹配项）或页面的 URL 可以进行查询，URL 方式仅适用于国家标准。

```bash
# 通过精确标准编号查询
openstd_spider info 'GB 18030-2022'
# 通过页面 URL 查询
openstd_spider info 'https://openstd.samr.gov.cn/bzgk/gb/newGbInfo?hcno=72969DAA3DA5795AD2163528FF57166C'
```

### 下载标准 pdf 文件

使用方式为子命令 `openstd_spider download`

```
Usage: openstd_spider download [OPTIONS] TARGET

 下载标准文件PDF

 Arguments
 *    target      TEXT  标准编号或url [required]

 Options
 --detail   -d            是否展示详细元数据
 --preview                强制下载预览版本
 --output   -o      PATH  下载路径或文件
 --help                   Show this message and exit.
```

以下说明针对**国家标准**。国家标准有两种公开方式，分别是仅允许预览和允许下载，这两种方式均可进行 PDF 文件下载，优先以直接下载方式下载，使用预览方式下载将无任何目录索引及可复制文本。

对于禁止预览和下载的标准文件，本项目无法下载。

### 行业标准与地方标准

行业标准、地方标准的全文不在国家标准全文公开系统内，且两者的获取方式互不相同，本项目会自动识别标准类别并选择对应来源：

| 标准类别 | 全文来源 | 获取方式 |
| --- | --- | --- |
| 行业标准 | [行业标准信息服务平台](https://hbba.sacinfo.org.cn/) | 逐页 PNG 在线预览，下载后拼接为 PDF |
| 地方标准 | [地方标准信息服务平台](https://dbba.sacinfo.org.cn/) | 站点直接提供 PDF，原样下载 |

两类标准均**无需人机验证码**。注意行业标准以页面图片形式提供，因此生成的 PDF 无目录索引及可复制文本。

标准类别的判定以检索平台的返回结果为准，而非标准编号前缀——因为 `DB` 既是地震行业标准代号、也是地方标准前缀，仅凭编号无法区分。

```bash
# 行业标准
openstd_spider download 'SL/T 858-2025'
# 地方标准
openstd_spider download 'DB11/T 1000.2-2021'
```

通过精确的标准编号（非精确的标准编号最多一个匹配项）或页面的 URL 可以进行下载；URL 方式仅适用于国家标准。

```bash
# 通过精确标准编号下载
openstd_spider download 'GB 18030-2022'
# 通过页面 URL 下载
openstd_spider download 'https://openstd.samr.gov.cn/bzgk/gb/newGbInfo?hcno=72969DAA3DA5795AD2163528FF57166C'
```

默认情况下 PDF 文件将下载到当前目录，并以标准编号命名，也可加`-o`参数指定输出路径或文件名。

## ✨Features

- 集成搜索、元数据查询、PDF 下载三个功能，通过子命令进行调用
- 支持国家标准、行业标准、地方标准三类标准文件，自动识别类别并选择对应全文来源
- 元数据查询和 PDF 下载支持自动识别 URL 或标准编号
- 查询结果及下载状态以 TUI 方式在终端显示，也可以输出为 json
- 自动识别下载时的人机验证码（仅国家标准需要）
- 预览方式下载自动拼接打乱的图块，并将图片生成 pdf 文件
- 检索结果包含 ICS/CCS、英文标题、归口单位、采标关系等丰富字段

## 🔌API

不仅可以通过 CLI 方式使用，也可以集成进其他项目，通过 API 调用

TODO: API 调用 Demo 及说明

## 🔨Building

克隆项目源码（可选）

```bash
git clone https://github.com/SocialSisterYi/OpenSTD_Spider
```

或从 Release 中下载源码包

安装项目依赖，请确保已经安装 pdm

```bash
pdm install
```

打包构建项目

```bash
pdm build
```

安装构建包到全局（可选）

```bash
pip install dist/openstd_spider-xxx.whl
```

## ⚠️Disclaimers

本项目以 GPL-3.0 License 作为开源协议，这意味着你需要遵守相应的规则

本项目仅适用于学习研究，任何人不得以此用于盈利

使用本项目造成的任何后果与本人无关
