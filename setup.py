from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="getscipapers_hoanganhduc",
    version="0.1.4",
    author="Duc A. Hoang (hoanganhduc)",
    author_email="anhduc.hoang1990@gmail.com",
    description="A Python package to get and request scientific papers from various sources",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/hoanganhduc/getscipapers",
    project_urls={
        "Homepage": "https://github.com/hoanganhduc/getscipapers",
        "Issues": "https://github.com/hoanganhduc/getscipapers/issues",
    },
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.10",
    license="GPL-3.0-or-later"
)
