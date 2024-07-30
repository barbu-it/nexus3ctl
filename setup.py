import os
from setuptools import setup

# Utility function to read the README file.
# Used for the long_description.  It's nice, because now 1) we have a top level
# README file and 2) it's easier to type in the README file than to put a raw
# string in below ...
def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(
    name = "nexus3ctl",
    version = "0.0.1",
    author = "Robin Cordier",
    author_email = "robin.cordier.pro@gmail.com",
    description = ("Nexus configuration importer/exporter and backup tool"),
    license = "BSD",
    keywords = "nexus nexus3 nexus3ctl",
    url = "http://packages.python.org/mrjk/",
    packages=['nexus3ctl'],
    long_description=read('README.md'),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Topic :: Utilities",
        "License :: OSI Approved :: BSD License",
    ],
    install_requires=[
        'typer>=0.12.3',
        'PyYAML>=6.0.1',
        'requests>=2.31.0',
    ],
    entry_points = {
        'console_scripts': ['nexus3ctl=nexus3ctl.nexus3ctl:cli_run'],
    },
)

