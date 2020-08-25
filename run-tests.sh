#!/usr/bin/env bash
# -*- coding: utf-8 -*-
#
# This file is part of Autobot.
# Copyright (C) 2015-2019 CERN.
#
# Autobot is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

black --check . && \
isort -rc -c -df && \
check-manifest --ignore ".travis-*" && \
pydocstyle autobot tests docs && \
sphinx-build -qnNW docs docs/_build/html && \
python -m pytest
