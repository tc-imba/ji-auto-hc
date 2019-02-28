"""
JI Auto HC
"""

from setuptools import setup

setup(
    name='ji-auto-hc',
    version='0.0.1',
    packages=['ji-auto-hc'],
    include_package_data=True,
    install_requires=[
        'click',
        'jinja2',
        'beautifulsoup4',
        'lxml',
        'aiohttp',
    ],
)
