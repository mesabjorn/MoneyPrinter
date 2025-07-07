from abc import ABC, abstractmethod
import hashlib
from pathlib import Path


class Cache(ABC):
    def hash_key(self, key):
        return hashlib.sha256(key.encode()).hexdigest()

    @abstractmethod
    def get(self, key):
        pass

    @abstractmethod
    def set(self, key, value):
        pass


class RequestCache(Cache):
    def __init__(self):
        self.cache = Path("./cache")
        self.cache.mkdir(parents=True, exist_ok=True)

    def get(self, key):
        h = self.hash_key(key)
        if (self.cache / h).exists():
            with open(self.cache / h, "r") as f:
                return f.read()
        return None

    def set(self, key, value):
        h = self.hash_key(key)
        with open(self.cache / h, "w") as f:
            f.write(value)

    def __str__(self):
        return str(self.cache)

    def __repr__(self):
        return self.__str__()
