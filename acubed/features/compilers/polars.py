# features/compilers/polars.py

import polars as pl


class PolarsCompiler:
    def column(self, expr):
        return pl.col(expr.name)

    def literal(self, expr):
        return pl.lit(expr.value)

    def add(self, expr):
        return expr.left.compile(self) + expr.right.compile(self)

    def divide(self, expr):
        return expr.left.compile(self) / expr.right.compile(self)

    def multiply(self, expr):
        return expr.left.compile(self) * expr.right.compile(self)

    def count(self, expr):
        return expr.expr.compile(self).count()

    def avg(self, expr):
        return expr.expr.compile(self).mean()

    def stddev(self, expr):
        return expr.expr.compile(self).std()

    def rolling_mean(self, expr):
        return expr.expr.compile(self).rolling_mean(expr.window_size)
