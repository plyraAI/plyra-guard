# Plyra namespace package — allows multiple plyra-* packages
# to coexist under the "plyra" namespace.
#
# See: https://packaging.python.org/en/latest/guides/packaging-namespace-packages/
from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)
