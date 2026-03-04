from setuptools import setup, find_packages

setup(
    name="logsentinel",
    version="1.0.0",
    description="AI-Powered Log Analyzer",
    author="Blade",
    author_email="blade@maleon.run",
    url="https://github.com/dablon/logsentinel",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "pyyaml>=6.0",
        "requests>=2.28.0",
    ],
    extras_require={
        "all": ["pytest", "pytest-cov"],
    },
    entry_points={
        "console_scripts": [
            "logsentinel=logsentinel:main_cli",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)
