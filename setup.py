from pathlib import Path

from setuptools import find_packages, setup

version = (Path(__file__).parent / "launchpad/VERSION").read_text("ascii").strip()

install_requires = [
    "temporalio>=1.6.0",
    "attrs>=23.2.0",
    "sanic>=23.12.1",
    "sanic-ext>=23.12.0",
    "requests>=2.32.3",
    "pyjwt>=2.8.0",
    "jinja2>=2.3.4",
    "click==8.0.1"
]

extras_require = {
    ':platform_python_implementation == "CPython"': ["PyDispatcher>=2.0.5"],
    ':platform_python_implementation == "PyPy"': ["PyPyDispatcher>=2.1.0"],
}

setup(
    name="Launchpad",
    version=version,
    project_urls={
        "Source": "https://github.com/morague/launchpad",
        "Issues": "https://github.com/morague/launchpad/issues"
    },
    authors = [{"name":"Romain Viry", "email":"rom88.viry@gmail.com"}],
    description = "Tasks orchestration tool based on temporalio",
    python_requires=">=3.10",
    install_requires=install_requires,
    extras_require=extras_require,
    packages=find_packages(where=".", exclude=("tests", "tests.*", "activities")),
    package_dir={"launchpad": "launchpad"},
    package_data={
        "templates": ["*.yaml", "*.py"],
        "templates.temporal": ["*.py"],
        "templates.deployments": ["*"],
        "templates.deployments.workers": ["*.yaml"],
        "templates.deployments.tasks": ["*.yaml"],

        "templates.deployments_examples": ["*"],
        "templates.deployments_examples.workers": ["*.yaml"],
        "templates.deployments_examples.tasks": ["*.yaml"],
        "templates.deployments_templates": ["*.yaml"],
    },
    include_package_data=True,
    zip_safe=False,
    entry_points={"console_scripts": ["launchpad = launchpad.cli.scripts:cli"]},
)