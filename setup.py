"""
Setup configuration for electrochemistry-r6244 package
"""

from setuptools import setup, find_packages
from pathlib import Path

ROOT = Path(__file__).resolve().parent
README = (ROOT / "README.md").read_text(encoding="utf-8")

setup(
    name="electrochemistry-r6244",
    version="1.0.0",
    description="Electrochemistry control application for R6244 potentiostat via GPIB",
    long_description=README,
    long_description_content_type="text/markdown",
    author="Science Tokyo",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.10",
    install_requires=[
        "rdkit>=2023.09",
        "pyvisa>=1.14",
        "pyvisa-py>=0.6",
        "matplotlib>=3.7",
        "numpy>=1.24",
        "pandas>=2.0",
    ],
    extras_require={
        "gpib": ["gpib-ctypes>=0.3.0"],
        "dev": ["pytest>=7.0", "black>=23.0", "pylint>=2.16"],
    },
    entry_points={
        "console_scripts": [
            "electrochemistry-r6244=app.gui:main",
        ],
    },
    package_data={
        "app": ["../config/default_config.json"],
    },
    include_package_data=True,
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Chemistry",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
