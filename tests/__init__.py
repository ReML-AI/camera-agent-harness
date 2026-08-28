"""Marks `tests` as a regular package.

Required, not cosmetic: ultralytics ships its own top-level `tests` package into
site-packages, and a regular package always shadows a namespace package regardless of
sys.path order. Without this file, `from tests.x import y` resolves to ultralytics'
tests on any machine where ultralytics is installed.
"""
