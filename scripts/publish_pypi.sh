#!/usr/bin/env bash
set -e

python -m pip install --upgrade build twine
python -m build
python -m twine upload dist/*
