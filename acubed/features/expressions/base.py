# features/expressions/base.py

from __future__ import annotations

from abc import ABC, abstractmethod


class Expression(ABC):
    @abstractmethod
    def compile(self, compiler):
        pass


class Column(Expression):
    def __init__(self, name: str):
        self.name = name

    def compile(self, compiler):
        return compiler.column(self)


class Literal(Expression):
    def __init__(self, value):
        self.value = value

    def compile(self, compiler):
        return compiler.literal(self)
