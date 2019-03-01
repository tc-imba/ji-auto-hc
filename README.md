# JI-Auto-HC

Warning! This tool will automatically send someone to the JI Honor Council.

## Requirements

+ `Python >= 3.6`
+ `xelatex`

The tool is currently only tested on Linux.

## Installation

```bash
pip install git+https://github.com/tc-imba/ji-auto-hc.git@master
```

## Usage

```bash
jiautohc -i sample.json -s students.csv
```

## Licence

Apache 2.0

## Dependencies

+ click
+ jinja2
+ beautifulsoup4
+ lxml
+ aiohttp

