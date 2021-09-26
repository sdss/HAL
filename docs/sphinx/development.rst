Development
===========

``HAL`` uses `poetry <http://poetry.eustace.io/>`__ for dependency management and packaging. To work with an editable install it's recommended that you setup ``poetry`` and install ``HAL`` in a virtual environment by doing ::

    poetry install

Pip does not support editable installs with PEP-517 yet. That means that running ``pip install -e .`` will fail because ``poetry`` doesn't use a ``setup.py`` file. As a workaround, you can use the ``create_setup.py`` file to generate a temporary ``setup.py`` file. To install ``HAL`` in editable mode without ``poetry``, do ::

    pip install --pre poetry
    python create_setup.py
    pip install -e .

Note that this will only install the production dependencies, not the development ones. You'll need to install those manually (see ``pyproject.toml`` ``[tool.poetry.dev-dependencies]``).

Style and type checking
-----------------------

This project uses the `black <https://github.com/psf/black>`__ code style with 88-character line lengths for code and docstrings. It is recommended that you run ``black`` on save. Imports must be sorted using `isort <https://pycqa.github.io/isort/>`__. The GitHub test workflow checks all the Python file to make sure they comply with the black formatting.

Configuration files for `flake8 <https://flake8.pycqa.org/en/latest/>`__, `isort <https://pycqa.github.io/isort/>`__, and `black <https://github.com/psf/black>`__ are provided and will be applied by most editors. For Visual Studio Code, the following project file is compatible with the project configuration: ::

    {
        "python.formatting.provider": "black",
        "[python]" : {
            "editor.codeActionsOnSave": {
                "source.organizeImports": true
            },
            "editor.formatOnSave": true
        },
        "[markdown]": {
            "editor.wordWrapColumn": 88
        },
        "[restructuredtext]": {
            "editor.wordWrapColumn": 88
        },
        "editor.rulers": [88],
        "editor.wordWrapColumn": 88,
        "python.analysis.typeCheckingMode": "basic"
    }

This assumes that the `Python <https://marketplace.visualstudio.com/items?itemName=ms-python.python>`__ and `Pylance <https://marketplace.visualstudio.com/items?itemName=ms-python.vscode-pylance>`__ extensions are installed.

This project uses `type hints <https://docs.python.org/3/library/typing.html>`__. Typing is enforced by the test workflow using `pyright <https://github.com/microsoft/pyright>`__ (in practice this means that if ``Pylance`` doesn't produce any errors in basic mode, ``pyright`` shouldn't).
