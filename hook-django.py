# Local replacement for PyInstaller's hook-django.py.
# The standard hook in PyInstaller 6.22.1 crashes while collecting
# Django migration scripts for this project.
#
# KIS Kalanso collects its application packages and migrations explicitly
# in KIS_Kalanso_Alpha.spec, so this hook intentionally does not perform
# Django's automatic migration discovery.
