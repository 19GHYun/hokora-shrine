# -*- coding: utf-8 -*-
"""Hokora — 작업표시줄 위의 나만의 신사 키우기.

  python hokora.pyw

  HOKORA_ALL=1    해금 안 된 캐릭터까지 모두 등장 (개발용)
  HOKORA_DEBUG=1  자세한 로그
"""
import sys

from hokora.app import main

if __name__ == "__main__":
    sys.exit(main())
