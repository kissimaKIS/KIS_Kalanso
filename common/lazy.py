"""Import différé des bibliothèques lourdes.

pandas met à lui seul ~1,5 s à s'importer. Il ne sert qu'aux imports Excel :
le charger au démarrage ralentissait chaque lancement de l'application.
"""
import importlib


class LazyModule:
    def __init__(self, name):
        self._name = name
        self._module = None

    def __getattr__(self, attr):
        if self._module is None:
            self._module = importlib.import_module(self._name)
        return getattr(self._module, attr)


pandas = LazyModule("pandas")
