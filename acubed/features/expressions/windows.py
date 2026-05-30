# features/expressions/windows.py

from .base import Expression


class RollingMean(Expression):
    def __init__(
        self,
        expr: Expression,
        window_size: int,
    ):
        self.expr = expr
        self.window_size = window_size

    def compile(self, compiler):
        return compiler.rolling_mean(self)
