from setuptools import setup, find_packages

VERSION = "2.0"
setup(
    name="moduvent",
    version=VERSION,
    description="A lightweight, modular event system for Python applications with plugin architecture support.",
    packages=find_packages(),
)
