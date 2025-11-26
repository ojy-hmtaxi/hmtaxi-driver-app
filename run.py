#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
애플리케이션 실행 스크립트
"""
from app import app

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

