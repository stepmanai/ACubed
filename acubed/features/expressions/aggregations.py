# features/expressions/aggregations.py

from .base import Expression


class Count(Expression):
    def __init__(self, expr: Expression):
        self.expr = expr

    def compile(self, compiler):
        return compiler.count(self)


class Avg(Expression):
    def __init__(self, expr: Expression):
        self.expr = expr

    def compile(self, compiler):
        return compiler.avg(self)


class StdDev(Expression):
    def __init__(self, expr: Expression):
        self.expr = expr

    def compile(self, compiler):
        return compiler.stddev(self)
